from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from lambdas.generate_upload_url.app import handle_upload_url
from shared.config import AppConfig


class FakeS3Client:
    def __init__(self) -> None:
        self.params = None

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.params = {
            "operation": operation,
            "Params": Params,
            "ExpiresIn": ExpiresIn,
        }
        return "https://example.test/upload"


class FakeTable:
    def __init__(self) -> None:
        self.item = None

    def put_item(self, **kwargs):
        self.item = kwargs["Item"]
        return {}


class GenerateUploadUrlTest(unittest.TestCase):
    def test_creates_document_record_and_presigned_url(self) -> None:
        config = AppConfig(
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
        )
        s3_client = FakeS3Client()
        table = FakeTable()
        event = {
            "body": json.dumps(
                {
                    "filename": "resume.pdf",
                    "documentType": "resume",
                    "contentType": "application/pdf",
                    "contentLength": 1024,
                }
            )
        }

        response = handle_upload_url(
            event,
            config=config,
            s3_client=s3_client,
            table=table,
            id_factory=lambda: "doc_test",
            now_factory=lambda: datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(response["statusCode"], 201)
        body = json.loads(response["body"])
        self.assertEqual(body["documentId"], "doc_test")
        self.assertEqual(body["s3Key"], "uploads/doc_test/resume.pdf")
        self.assertEqual(table.item["status"], "UPLOADED")
        self.assertEqual(table.item["expiresAt"], 1779192000)
        self.assertEqual(s3_client.params["Params"]["ContentType"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
