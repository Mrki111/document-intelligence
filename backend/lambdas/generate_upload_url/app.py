from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping
from uuid import uuid4

from shared.config import AppConfig, load_config
from shared.constants import STATUS_UPLOADED
from shared.response import BadRequestError, json_response, parse_json_body
from shared.validation import ValidationError, validate_upload_request


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    config = load_config()
    try:
        return handle_upload_url(event, config=config)
    except (BadRequestError, ValidationError) as exc:
        return json_response(400, {"message": str(exc)})
    except Exception:
        return json_response(500, {"message": "Internal server error."})


def handle_upload_url(
    event: Mapping[str, Any],
    *,
    config: AppConfig,
    s3_client: Any | None = None,
    table: Any | None = None,
    id_factory: Callable[[], str] | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    if not config.upload_bucket or not config.table_name:
        raise RuntimeError("UPLOAD_BUCKET and TABLE_NAME must be configured.")

    payload = parse_json_body(event)
    upload = validate_upload_request(
        payload,
        allowed_document_types=config.allowed_document_types,
        max_content_length=config.max_content_length,
    )

    document_id = (id_factory or _new_document_id)()
    now = (now_factory or _utc_now)()
    expires_at = int((now + timedelta(days=config.record_ttl_days)).timestamp())
    s3_key = f"{config.upload_prefix}{document_id}/{upload.filename}"

    table = table or _document_table(config.table_name)
    s3_client = s3_client or _s3_client()

    table.put_item(
        Item={
            "documentId": document_id,
            "documentType": upload.document_type,
            "filename": upload.filename,
            "contentType": upload.content_type,
            "contentLength": upload.content_length,
            "s3Key": s3_key,
            "status": STATUS_UPLOADED,
            "createdAt": _isoformat(now),
            "updatedAt": _isoformat(now),
            "expiresAt": expires_at,
        },
        ConditionExpression="attribute_not_exists(documentId)",
    )

    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": config.upload_bucket,
            "Key": s3_key,
            "ContentType": upload.content_type,
        },
        ExpiresIn=config.upload_url_expiration_seconds,
    )

    return json_response(
        201,
        {
            "documentId": document_id,
            "uploadUrl": upload_url,
            "s3Key": s3_key,
        },
    )


def _new_document_id() -> str:
    return f"doc_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _s3_client() -> Any:
    import boto3

    return boto3.client("s3")


def _document_table(table_name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(table_name)
