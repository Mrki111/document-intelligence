from __future__ import annotations

import unittest
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from lambdas.process_document.app import handle_s3_event
from shared.config import AppConfig


class FakeS3Client:
    def __init__(self, *, content_length=1024, content_type="application/pdf") -> None:
        self.content_length = content_length
        self.content_type = content_type
        self.head_calls = 0

    def head_object(self, *, Bucket, Key):
        self.head_calls += 1
        return {
            "ContentLength": self.content_length,
            "ContentType": self.content_type,
        }


class FakeTextractClient:
    def __init__(self, *, error: ClientError | None = None) -> None:
        self.start_calls = []
        self.error = error

    def start_document_text_detection(self, **kwargs):
        self.start_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"JobId": "textract-job-123"}


class FakeTable:
    def __init__(self, item, *, complete_before_failure: bool = False, complete_update_conflict: bool = False) -> None:
        self.item = item
        self.updates = []
        self.complete_before_failure = complete_before_failure
        self.complete_update_conflict = complete_update_conflict

    def get_item(self, *, Key):
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        values = kwargs["ExpressionAttributeValues"]

        if ":failed" in values and ":reason" in values:
            if self.complete_before_failure:
                self.item["status"] = "COMPLETED"
            if self.item.get("status") == "COMPLETED":
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["status"] = values[":failed"]
            self.item["failureReason"] = values[":reason"]
            self.item["errorMessage"] = values[":message"]
            return {}

        if ":completed" in values:
            if self.complete_update_conflict:
                self.item["status"] = "COMPLETED"
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["status"] = values[":completed"]
            self.item["updatedAt"] = values[":updated_at"]
            self.item["extractedTextPreview"] = values[":preview"]
            self.item["extractedTextLength"] = values[":length"]
            if ":s3_etag" in values:
                self.item["s3ETag"] = values[":s3_etag"]
            if ":analysis" in values:
                self.item["analysis"] = values[":analysis"]
            return {}

        if ":job_id" in values:
            if self.complete_update_conflict:
                self.item["status"] = "COMPLETED"
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["updatedAt"] = values[":updated_at"]
            self.item["textractJobId"] = values[":job_id"]
            self.item["textractJobStartedAt"] = values[":started_at"]
            if ":s3_etag" in values:
                self.item["s3ETag"] = values[":s3_etag"]
            return {}

        if ":processing" in values and ":uploaded" in values:
            current_status = self.item.get("status")
            updated_at = self.item.get("updatedAt")
            stale_threshold = values[":stale_threshold"]
            allowed = current_status in ("UPLOADED", "FAILED") or (
                current_status == "PROCESSING"
                and isinstance(updated_at, str)
                and updated_at < stale_threshold
            )
            if not allowed:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["status"] = values[":processing"]
            self.item["updatedAt"] = values[":updated_at"]
            return {}

        return {}


def config() -> AppConfig:
    return AppConfig(
        upload_bucket="uploads-bucket",
        table_name="documents",
        allowed_document_types=("resume", "invoice", "general"),
        max_content_length=10485760,
        upload_prefix="uploads/",
        upload_url_expiration_seconds=900,
        record_ttl_days=7,
        extracted_text_preview_length=1000,
        bedrock_model_id=None,
        bedrock_text_limit=12000,
        stale_processing_seconds=600,
        textract_sns_topic_arn="arn:aws:sns:us-east-1:123456789012:textract-completion",
        textract_role_arn="arn:aws:iam::123456789012:role/textract-publish",
        max_textract_pages=25,
    )


def s3_event() -> dict:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "uploads-bucket"},
                    "object": {"key": "uploads/doc_test/resume.pdf", "eTag": "etag123"},
                }
            }
        ]
    }


class ProcessDocumentTest(unittest.TestCase):
    def test_starts_async_textract_job_for_uploaded_document(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "UPLOADED",
            }
        )
        textract = FakeTextractClient()

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=FakeS3Client(),
            textract_client=textract,
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["results"][0]["status"], "PROCESSING")
        self.assertEqual(result["results"][0]["textractJobId"], "textract-job-123")
        self.assertEqual(len(textract.start_calls), 1)
        self.assertEqual(table.item["status"], "PROCESSING")
        self.assertEqual(table.item["textractJobId"], "textract-job-123")
        self.assertEqual(table.item["s3ETag"], "etag123")
        request = textract.start_calls[0]
        self.assertEqual(request["JobTag"], "doc_test")
        self.assertEqual(request["DocumentLocation"]["S3Object"]["Name"], "uploads/doc_test/resume.pdf")
        self.assertEqual(
            request["NotificationChannel"]["SNSTopicArn"],
            "arn:aws:sns:us-east-1:123456789012:textract-completion",
        )

    def test_ignores_duplicate_completed_event(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "COMPLETED",
            }
        )
        s3 = FakeS3Client()
        textract = FakeTextractClient()

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=s3,
            textract_client=textract,
            table=table,
        )

        self.assertEqual(result["results"][0]["status"], "IGNORED_COMPLETED")
        self.assertEqual(s3.head_calls, 0)
        self.assertEqual(len(textract.start_calls), 0)

    def test_ignores_recent_processing_event(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "PROCESSING",
                "updatedAt": "2026-05-12T11:59:00Z",
            }
        )
        s3 = FakeS3Client()
        textract = FakeTextractClient()

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=s3,
            textract_client=textract,
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "IGNORED_PROCESSING")
        self.assertEqual(s3.head_calls, 0)
        self.assertEqual(len(textract.start_calls), 0)

    def test_recovers_stale_processing_record(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "PROCESSING",
                "updatedAt": "2026-05-12T11:30:00Z",
            }
        )

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=FakeS3Client(),
            textract_client=FakeTextractClient(),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "PROCESSING")
        self.assertEqual(table.item["status"], "PROCESSING")
        self.assertEqual(table.item["textractJobId"], "textract-job-123")

    def test_marks_invalid_upload_failed(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "UPLOADED",
            }
        )

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=FakeS3Client(content_type="application/octet-stream"),
            textract_client=FakeTextractClient(),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "FAILED")
        self.assertEqual(table.item["status"], "FAILED")
        self.assertEqual(table.item["failureReason"], "INVALID_UPLOAD_CONTENT_TYPE")

    def test_job_update_conflict_does_not_mark_completed_document_failed(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "PROCESSING",
                "updatedAt": "2026-05-12T11:30:00Z",
            },
            complete_update_conflict=True,
        )

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=FakeS3Client(),
            textract_client=FakeTextractClient(),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "IGNORED_CONCURRENT_UPDATE")
        self.assertEqual(table.item["status"], "COMPLETED")
        self.assertNotIn("failureReason", table.item)

    def test_failed_update_does_not_overwrite_completed_document(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "UPLOADED",
            },
            complete_before_failure=True,
        )

        result = handle_s3_event(
            s3_event(),
            config=config(),
            s3_client=FakeS3Client(content_type="application/octet-stream"),
            textract_client=FakeTextractClient(),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "IGNORED_COMPLETED")
        self.assertEqual(table.item["status"], "COMPLETED")
        self.assertNotIn("failureReason", table.item)

    def test_retryable_aws_error_is_raised_for_lambda_retry(self) -> None:
        table = FakeTable(
            {
                "documentId": "doc_test",
                "documentType": "resume",
                "contentLength": 1024,
                "s3Key": "uploads/doc_test/resume.pdf",
                "status": "UPLOADED",
            }
        )
        textract_error = ClientError(
            {
                "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"},
                "ResponseMetadata": {"HTTPStatusCode": 400},
            },
            "StartDocumentTextDetection",
        )

        with self.assertRaises(ClientError):
            handle_s3_event(
                s3_event(),
                config=config(),
                s3_client=FakeS3Client(),
                textract_client=FakeTextractClient(error=textract_error),
                table=table,
                now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
            )

        self.assertEqual(table.item["status"], "FAILED")
        self.assertEqual(table.item["failureReason"], "RETRYABLE_AWS_ERROR")


if __name__ == "__main__":
    unittest.main()
