from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping

from shared.constants import (
    DEFAULT_ALLOWED_DOCUMENT_TYPES,
    DEFAULT_BEDROCK_TEXT_LIMIT,
    DEFAULT_EXTRACTED_TEXT_PREVIEW_LENGTH,
    DEFAULT_MAX_CONTENT_LENGTH,
    DEFAULT_MAX_TEXTRACT_PAGES,
    DEFAULT_RECORD_TTL_DAYS,
    DEFAULT_STALE_PROCESSING_SECONDS,
    DEFAULT_UPLOAD_PREFIX,
    DEFAULT_UPLOAD_URL_EXPIRATION_SECONDS,
)


@dataclass(frozen=True)
class AppConfig:
    upload_bucket: str
    table_name: str
    allowed_document_types: tuple[str, ...]
    max_content_length: int
    upload_prefix: str
    upload_url_expiration_seconds: int
    record_ttl_days: int
    extracted_text_preview_length: int
    bedrock_model_id: str | None
    bedrock_text_limit: int
    stale_processing_seconds: int
    textract_sns_topic_arn: str | None = None
    textract_role_arn: str | None = None
    max_textract_pages: int = DEFAULT_MAX_TEXTRACT_PAGES

    def __post_init__(self) -> None:
        if self.max_textract_pages <= 0:
            raise ValueError("max_textract_pages must be greater than 0.")


def _int_from_env(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value in (None, ""):
        return default
    return int(value)


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    source = environ if env is None else env
    allowed_types = tuple(
        value.strip().lower()
        for value in source.get("ALLOWED_DOCUMENT_TYPES", ",".join(DEFAULT_ALLOWED_DOCUMENT_TYPES)).split(",")
        if value.strip()
    )

    return AppConfig(
        upload_bucket=source.get("UPLOAD_BUCKET", ""),
        table_name=source.get("TABLE_NAME", ""),
        allowed_document_types=allowed_types or DEFAULT_ALLOWED_DOCUMENT_TYPES,
        max_content_length=_int_from_env(source, "MAX_CONTENT_LENGTH", DEFAULT_MAX_CONTENT_LENGTH),
        upload_prefix=source.get("UPLOAD_PREFIX", DEFAULT_UPLOAD_PREFIX),
        upload_url_expiration_seconds=_int_from_env(
            source,
            "UPLOAD_URL_EXPIRATION_SECONDS",
            DEFAULT_UPLOAD_URL_EXPIRATION_SECONDS,
        ),
        record_ttl_days=_int_from_env(source, "RECORD_TTL_DAYS", DEFAULT_RECORD_TTL_DAYS),
        extracted_text_preview_length=_int_from_env(
            source,
            "EXTRACTED_TEXT_PREVIEW_LENGTH",
            DEFAULT_EXTRACTED_TEXT_PREVIEW_LENGTH,
        ),
        bedrock_model_id=source.get("BEDROCK_MODEL_ID") or None,
        bedrock_text_limit=_int_from_env(source, "BEDROCK_TEXT_LIMIT", DEFAULT_BEDROCK_TEXT_LIMIT),
        stale_processing_seconds=_int_from_env(
            source,
            "STALE_PROCESSING_SECONDS",
            DEFAULT_STALE_PROCESSING_SECONDS,
        ),
        textract_sns_topic_arn=source.get("TEXTRACT_SNS_TOPIC_ARN") or None,
        textract_role_arn=source.get("TEXTRACT_ROLE_ARN") or None,
        max_textract_pages=_int_from_env(source, "MAX_TEXTRACT_PAGES", DEFAULT_MAX_TEXTRACT_PAGES),
    )
