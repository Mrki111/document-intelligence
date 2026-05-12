from __future__ import annotations

import unittest

from shared.validation import ValidationError, validate_upload_request


class ValidationTest(unittest.TestCase):
    def test_valid_upload_request_is_normalized(self) -> None:
        upload = validate_upload_request(
            {
                "filename": "Resume.pdf",
                "documentType": "Resume",
                "contentType": "APPLICATION/PDF",
                "contentLength": 1024,
            },
            allowed_document_types=("resume", "invoice", "general"),
            max_content_length=2048,
        )

        self.assertEqual(upload.filename, "Resume.pdf")
        self.assertEqual(upload.document_type, "resume")
        self.assertEqual(upload.content_type, "application/pdf")
        self.assertEqual(upload.content_length, 1024)

    def test_rejects_path_traversal_filename(self) -> None:
        with self.assertRaisesRegex(ValidationError, "filename"):
            validate_upload_request(
                {
                    "filename": "../resume.pdf",
                    "documentType": "resume",
                    "contentType": "application/pdf",
                    "contentLength": 1024,
                },
                allowed_document_types=("resume",),
                max_content_length=2048,
            )

    def test_rejects_oversized_upload(self) -> None:
        with self.assertRaisesRegex(ValidationError, "contentLength"):
            validate_upload_request(
                {
                    "filename": "resume.pdf",
                    "documentType": "resume",
                    "contentType": "application/pdf",
                    "contentLength": 2049,
                },
                allowed_document_types=("resume",),
                max_content_length=2048,
            )


if __name__ == "__main__":
    unittest.main()
