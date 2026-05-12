from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ValidationError(ValueError):
    """Raised when user input fails validation."""


_PDF_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.pdf$", re.IGNORECASE)


@dataclass(frozen=True)
class UploadRequest:
    filename: str
    document_type: str
    content_type: str
    content_length: int


def validate_upload_request(
    payload: Mapping[str, Any],
    *,
    allowed_document_types: Iterable[str],
    max_content_length: int,
) -> UploadRequest:
    filename = _require_string(payload, "filename")
    document_type = _require_string(payload, "documentType").lower()
    content_type = _require_string(payload, "contentType").lower()
    content_length = _require_positive_int(payload, "contentLength")

    if "/" in filename or "\\" in filename or not _PDF_FILENAME_RE.fullmatch(filename):
        raise ValidationError("filename must be a simple .pdf filename.")

    if content_type != "application/pdf":
        raise ValidationError("contentType must be application/pdf.")

    allowed = {value.lower() for value in allowed_document_types}
    if document_type not in allowed:
        raise ValidationError(f"documentType must be one of: {', '.join(sorted(allowed))}.")

    if content_length > max_content_length:
        raise ValidationError(f"contentLength must be less than or equal to {max_content_length} bytes.")

    return UploadRequest(
        filename=filename,
        document_type=document_type,
        content_type=content_type,
        content_length=content_length,
    )


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} is required.")
    return value.strip()


def _require_positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{key} must be an integer.")
    if value <= 0:
        raise ValidationError(f"{key} must be greater than 0.")
    return value
