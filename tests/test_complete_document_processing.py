from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from io import BytesIO

from botocore.exceptions import ClientError

from lambdas.complete_document_processing.app import handle_sns_event
from shared.config import AppConfig


class FakeTextractClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls = []

    def get_document_text_detection(self, **kwargs):
        self.calls.append(kwargs)
        if "NextToken" in kwargs:
            index = int(kwargs["NextToken"])
        else:
            index = 0
        response = dict(self.responses[index])
        if index + 1 < len(self.responses):
            response["NextToken"] = str(index + 1)
        return response


class FakeBedrockClient:
    def __init__(self) -> None:
        self.calls = []

    def invoke_model(self, *, modelId, contentType, accept, body):
        self.calls.append(
            {
                "modelId": modelId,
                "contentType": contentType,
                "accept": accept,
                "body": body,
            }
        )
        analysis = {
            "summary": "AWS engineer with RAG experience.",
            "candidateLevel": "Mid-level",
            "skills": ["AWS", "Python", "RAG"],
            "awsServicesMentioned": ["S3", "Lambda"],
            "strengths": ["Production AI experience"],
            "weaknesses": [],
            "missingKeywords": [],
            "recommendedProjects": [],
            "atsScore": 82,
        }
        payload = {"content": [{"type": "text", "text": json.dumps(analysis)}]}
        return {"body": BytesIO(json.dumps(payload).encode("utf-8"))}


class FakeTable:
    def __init__(self, item) -> None:
        self.item = item
        self.updates = []

    def get_item(self, *, Key):
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        values = kwargs["ExpressionAttributeValues"]

        if ":preview" in values:
            if self.item.get("status") != "PROCESSING" or self.item.get("textractJobId") != values[":job_id"]:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["status"] = values[":completed"]
            self.item["updatedAt"] = values[":updated_at"]
            self.item["extractedTextPreview"] = values[":preview"]
            self.item["extractedTextLength"] = values[":length"]
            self.item["pageCount"] = values[":page_count"]
            if ":analysis" in values:
                self.item["analysis"] = values[":analysis"]
            return {}

        if ":failed" in values:
            if self.item.get("status") == "COMPLETED" or self.item.get("textractJobId") != values[":job_id"]:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "blocked"}},
                    "UpdateItem",
                )
            self.item["status"] = values[":failed"]
            self.item["updatedAt"] = values[":updated_at"]
            self.item["failureReason"] = values[":reason"]
            self.item["errorMessage"] = values[":message"]
            return {}

        return {}


def config(*, bedrock_model_id: str | None = None, max_textract_pages: int = 25) -> AppConfig:
    return AppConfig(
        upload_bucket="uploads-bucket",
        table_name="documents",
        allowed_document_types=("resume", "invoice", "general"),
        max_content_length=10485760,
        upload_prefix="uploads/",
        upload_url_expiration_seconds=900,
        record_ttl_days=7,
        extracted_text_preview_length=1000,
        bedrock_model_id=bedrock_model_id,
        bedrock_text_limit=12000,
        stale_processing_seconds=600,
        textract_sns_topic_arn="arn:aws:sns:us-east-1:123456789012:textract-completion",
        textract_role_arn="arn:aws:iam::123456789012:role/textract-publish",
        max_textract_pages=max_textract_pages,
    )


def document_item(*, status: str = "PROCESSING", job_id: str = "textract-job-123") -> dict:
    return {
        "documentId": "doc_test",
        "documentType": "resume",
        "filename": "resume.pdf",
        "status": status,
        "textractJobId": job_id,
    }


def sns_event(*, status: str = "SUCCEEDED", job_id: str = "textract-job-123", document_id: str = "doc_test") -> dict:
    return {
        "Records": [
            {
                "Sns": {
                    "Message": json.dumps(
                        {
                            "JobId": job_id,
                            "Status": status,
                            "API": "StartDocumentTextDetection",
                            "JobTag": document_id,
                        }
                    )
                }
            }
        ]
    }


def textract_pages(*, pages: int = 2) -> list[dict]:
    return [
        {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": {"Pages": pages},
            "Blocks": [
                {"BlockType": "PAGE", "Page": 1},
                {"BlockType": "LINE", "Page": 1, "Text": "Page one"},
            ],
        },
        {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": {"Pages": pages},
            "Blocks": [
                {"BlockType": "PAGE", "Page": 2},
                {"BlockType": "LINE", "Page": 2, "Text": "Page two"},
            ],
        },
    ]


class CompleteDocumentProcessingTest(unittest.TestCase):
    def test_completes_multi_page_textract_job(self) -> None:
        table = FakeTable(document_item())
        textract = FakeTextractClient(textract_pages())

        result = handle_sns_event(
            sns_event(),
            config=config(),
            textract_client=textract,
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["results"][0]["status"], "COMPLETED")
        self.assertEqual(result["results"][0]["pageCount"], 2)
        self.assertEqual(len(textract.calls), 2)
        self.assertEqual(table.item["status"], "COMPLETED")
        self.assertEqual(table.item["extractedTextPreview"], "Page one\nPage two")
        self.assertEqual(table.item["extractedTextLength"], 17)
        self.assertEqual(table.item["pageCount"], 2)

    def test_stores_bedrock_analysis_after_textract_completion(self) -> None:
        table = FakeTable(document_item())
        bedrock = FakeBedrockClient()

        result = handle_sns_event(
            sns_event(),
            config=config(bedrock_model_id="anthropic.claude-3-5-haiku-20241022-v1:0"),
            textract_client=FakeTextractClient(textract_pages()),
            table=table,
            bedrock_client=bedrock,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "COMPLETED")
        self.assertEqual(len(bedrock.calls), 1)
        self.assertEqual(bedrock.calls[0]["modelId"], "anthropic.claude-3-5-haiku-20241022-v1:0")
        self.assertEqual(table.item["analysis"]["summary"], "AWS engineer with RAG experience.")
        self.assertEqual(table.item["analysis"]["atsScore"], 82)

    def test_failed_textract_notification_marks_document_failed(self) -> None:
        table = FakeTable(document_item())

        result = handle_sns_event(
            sns_event(status="FAILED"),
            config=config(),
            textract_client=FakeTextractClient(textract_pages()),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "FAILED")
        self.assertEqual(table.item["status"], "FAILED")
        self.assertEqual(table.item["failureReason"], "TEXTRACT_JOB_FAILED")

    def test_ignores_stale_textract_job_notification(self) -> None:
        table = FakeTable(document_item(job_id="current-job"))

        result = handle_sns_event(
            sns_event(job_id="old-job"),
            config=config(),
            textract_client=FakeTextractClient(textract_pages()),
            table=table,
        )

        self.assertEqual(result["results"][0]["status"], "IGNORED_STALE_JOB")
        self.assertEqual(table.item["status"], "PROCESSING")

    def test_rejects_documents_over_page_limit(self) -> None:
        table = FakeTable(document_item())

        result = handle_sns_event(
            sns_event(),
            config=config(max_textract_pages=1),
            textract_client=FakeTextractClient(textract_pages(pages=2)),
            table=table,
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["results"][0]["status"], "FAILED")
        self.assertEqual(table.item["failureReason"], "DOCUMENT_TOO_MANY_PAGES")


if __name__ == "__main__":
    unittest.main()
