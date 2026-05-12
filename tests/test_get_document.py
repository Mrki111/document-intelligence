from __future__ import annotations

import json
import unittest

from lambdas.get_document.app import handle_get_document
from shared.config import AppConfig


class FakeTable:
    def __init__(self, item=None) -> None:
        self.item = item

    def get_item(self, *, Key):
        return {"Item": self.item} if self.item else {}


def config() -> AppConfig:
    return AppConfig(
        upload_bucket="uploads-bucket",
        table_name="documents",
        allowed_document_types=("resume",),
        max_content_length=1024,
        upload_prefix="uploads/",
        upload_url_expiration_seconds=900,
        record_ttl_days=7,
        extracted_text_preview_length=1000,
        bedrock_model_id=None,
        bedrock_text_limit=12000,
        stale_processing_seconds=600,
    )


class GetDocumentTest(unittest.TestCase):
    def test_returns_minimal_body_for_processing_status(self) -> None:
        response = handle_get_document(
            {"pathParameters": {"documentId": "doc_test"}},
            config=config(),
            table=FakeTable(
                {
                    "documentId": "doc_test",
                    "status": "PROCESSING",
                    "expiresAt": 1779192000,
                    "contentLength": 1024,
                }
            ),
        )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body, {"documentId": "doc_test", "status": "PROCESSING"})

    def test_returns_completed_fields(self) -> None:
        response = handle_get_document(
            {"pathParameters": {"documentId": "doc_test"}},
            config=config(),
            table=FakeTable(
                {
                    "documentId": "doc_test",
                    "status": "COMPLETED",
                    "documentType": "resume",
                    "filename": "resume.pdf",
                    "extractedTextPreview": "John Smith",
                    "analysis": {"summary": "Cloud engineer"},
                    "expiresAt": 1779192000,
                }
            ),
        )

        body = json.loads(response["body"])
        self.assertEqual(
            body,
            {
                "documentId": "doc_test",
                "status": "COMPLETED",
                "documentType": "resume",
                "filename": "resume.pdf",
                "extractedTextPreview": "John Smith",
                "analysis": {"summary": "Cloud engineer"},
            },
        )

    def test_returns_failed_fields(self) -> None:
        response = handle_get_document(
            {"pathParameters": {"documentId": "doc_test"}},
            config=config(),
            table=FakeTable(
                {
                    "documentId": "doc_test",
                    "status": "FAILED",
                    "documentType": "resume",
                    "filename": "resume.pdf",
                    "failureReason": "INVALID_UPLOAD_SIZE",
                    "errorMessage": "Uploaded object size is not allowed.",
                    "expiresAt": 1779192000,
                }
            ),
        )

        body = json.loads(response["body"])
        self.assertEqual(
            body,
            {
                "documentId": "doc_test",
                "status": "FAILED",
                "documentType": "resume",
                "filename": "resume.pdf",
                "failureReason": "INVALID_UPLOAD_SIZE",
                "errorMessage": "Uploaded object size is not allowed.",
            },
        )

    def test_returns_404_for_missing_document(self) -> None:
        response = handle_get_document(
            {"pathParameters": {"documentId": "doc_missing"}},
            config=config(),
            table=FakeTable(),
        )

        self.assertEqual(response["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
