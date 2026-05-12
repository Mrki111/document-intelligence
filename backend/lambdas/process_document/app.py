from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping
from urllib.parse import unquote_plus

from botocore.exceptions import ClientError

from shared.bedrock import BedrockOutputError, invoke_bedrock_json
from shared.config import AppConfig, load_config
from shared.constants import STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING, STATUS_UPLOADED
from shared.textract import extract_text

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.safe_message = message


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    config = load_config()
    return handle_s3_event(event, config=config)


def handle_s3_event(
    event: Mapping[str, Any],
    *,
    config: AppConfig,
    s3_client: Any | None = None,
    textract_client: Any | None = None,
    table: Any | None = None,
    bedrock_client: Any | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    if not config.table_name:
        raise RuntimeError("TABLE_NAME must be configured.")

    s3_client = s3_client or _s3_client()
    textract_client = textract_client or _textract_client()
    table = table or _document_table(config.table_name)
    if config.bedrock_model_id and bedrock_client is None:
        bedrock_client = _bedrock_client()

    results = []
    for record in event.get("Records", []):
        now = (now_factory or _utc_now)()
        result = process_record(
            record,
            config=config,
            s3_client=s3_client,
            textract_client=textract_client,
            table=table,
            bedrock_client=bedrock_client,
            now=now,
        )
        results.append(result)
    return {"processed": len(results), "results": results}


def process_record(
    record: Mapping[str, Any],
    *,
    config: AppConfig,
    s3_client: Any,
    textract_client: Any,
    table: Any,
    bedrock_client: Any | None,
    now: datetime,
) -> dict[str, Any]:
    bucket, key = _bucket_and_key(record)
    document_id = _document_id_from_key(key, config.upload_prefix)
    if document_id is None:
        logger.info("Skipping S3 object outside upload prefix: %s", key)
        return {"status": "SKIPPED", "s3Key": key}

    item = _load_document(table, document_id)
    if item is None:
        logger.warning("No DynamoDB record found for documentId=%s", document_id)
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "MISSING_RECORD"}

    if item.get("status") == STATUS_COMPLETED:
        logger.info("Ignoring duplicate event for completed documentId=%s", document_id)
        return {"documentId": document_id, "status": "IGNORED_COMPLETED"}

    stale_threshold = _isoformat(now - timedelta(seconds=config.stale_processing_seconds))
    if item.get("status") == STATUS_PROCESSING and not _is_stale_processing(item, stale_threshold):
        logger.info("Ignoring duplicate event for processing documentId=%s", document_id)
        return {"documentId": document_id, "status": "IGNORED_PROCESSING"}

    try:
        _validate_uploaded_object(
            item=item,
            bucket=bucket,
            key=key,
            config=config,
            s3_client=s3_client,
        )
        if not _mark_processing(table, document_id, now, stale_threshold):
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}

        textract_response = textract_client.detect_document_text(
            Document={"S3Object": {"Bucket": bucket, "Name": key}}
        )
        text = extract_text(textract_response)
        preview = text[: config.extracted_text_preview_length]

        analysis = None
        if config.bedrock_model_id:
            # bedrock_text_limit is applied inside build_prompt as a safety net;
            # the full extracted text is passed in so the limit is enforced in one place.
            analysis = invoke_bedrock_json(
                bedrock_client,
                model_id=config.bedrock_model_id,
                document_type=item["documentType"],
                extracted_text=text,
                text_limit=config.bedrock_text_limit,
            )

        completed = _mark_completed(
            table,
            document_id=document_id,
            now=now,
            extracted_text_preview=preview,
            extracted_text_length=len(text),
            analysis=analysis,
            s3_etag=record.get("s3", {}).get("object", {}).get("eTag"),
        )
        if not completed:
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_COMPLETED}
    except ProcessingError as exc:
        if not _mark_failed(table, document_id, now, exc.reason, exc.safe_message):
            return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": exc.reason}
    except BedrockOutputError as exc:
        if not _mark_failed(table, document_id, now, "BEDROCK_INVALID_OUTPUT", str(exc)):
            return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "BEDROCK_INVALID_OUTPUT"}
    except ClientError as exc:
        if _is_retryable_client_error(exc):
            logger.warning("Retryable AWS error for documentId=%s: %s", document_id, exc)
            if _mark_failed(
                table,
                document_id,
                now,
                "RETRYABLE_AWS_ERROR",
                "Temporary AWS service error. Processing will be retried.",
            ):
                raise
            return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
        logger.exception("AWS client error while processing documentId=%s", document_id)
        if not _mark_failed(table, document_id, now, "AWS_CLIENT_ERROR", "AWS service call failed."):
            return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "AWS_CLIENT_ERROR"}
    except Exception:
        logger.exception("Processing failed for documentId=%s", document_id)
        if not _mark_failed(table, document_id, now, "PROCESSING_FAILED", "Document processing failed."):
            return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "PROCESSING_FAILED"}


def _bucket_and_key(record: Mapping[str, Any]) -> tuple[str, str]:
    s3 = record["s3"]
    return s3["bucket"]["name"], unquote_plus(s3["object"]["key"])


def _document_id_from_key(key: str, upload_prefix: str) -> str | None:
    if not key.startswith(upload_prefix) or not key.lower().endswith(".pdf"):
        return None
    remainder = key[len(upload_prefix) :]
    parts = remainder.split("/", 1)
    if len(parts) != 2 or not parts[0]:
        return None
    return parts[0]


def _load_document(table: Any, document_id: str) -> dict[str, Any] | None:
    response = table.get_item(Key={"documentId": document_id})
    return response.get("Item")


def _is_stale_processing(item: Mapping[str, Any], stale_threshold: str) -> bool:
    # ISO 8601 UTC strings produced by _isoformat sort lexicographically,
    # so a string compare is equivalent to a timestamp compare.
    updated_at = item.get("updatedAt")
    return isinstance(updated_at, str) and updated_at < stale_threshold


def _validate_uploaded_object(
    *,
    item: Mapping[str, Any],
    bucket: str,
    key: str,
    config: AppConfig,
    s3_client: Any,
) -> None:
    if key != item.get("s3Key"):
        raise ProcessingError("INVALID_UPLOAD_KEY", "Uploaded object key does not match the document record.")

    head = s3_client.head_object(Bucket=bucket, Key=key)
    actual_length = int(head.get("ContentLength", 0))
    actual_content_type = str(head.get("ContentType", "")).split(";", 1)[0].lower()

    if actual_length <= 0 or actual_length > config.max_content_length:
        raise ProcessingError("INVALID_UPLOAD_SIZE", "Uploaded object size is not allowed.")
    if item.get("contentLength") and actual_length != int(item["contentLength"]):
        raise ProcessingError("INVALID_UPLOAD_SIZE", "Uploaded object size does not match the request.")
    if actual_content_type != "application/pdf":
        raise ProcessingError("INVALID_UPLOAD_CONTENT_TYPE", "Uploaded object must be application/pdf.")


def _mark_processing(table: Any, document_id: str, now: datetime, stale_threshold: str) -> bool:
    try:
        table.update_item(
            Key={"documentId": document_id},
            UpdateExpression="SET #status = :processing, updatedAt = :updated_at",
            ConditionExpression=(
                "#status IN (:uploaded, :failed) "
                "OR (#status = :processing AND updatedAt < :stale_threshold)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":processing": STATUS_PROCESSING,
                ":uploaded": STATUS_UPLOADED,
                ":failed": STATUS_FAILED,
                ":updated_at": _isoformat(now),
                ":stale_threshold": stale_threshold,
            },
        )
        return True
    except ClientError as exc:
        if _is_conditional_check_failed(exc):
            logger.info("Conditional status update skipped for documentId=%s", document_id)
            return False
        raise


def _mark_completed(
    table: Any,
    *,
    document_id: str,
    now: datetime,
    extracted_text_preview: str,
    extracted_text_length: int,
    analysis: dict[str, Any] | None,
    s3_etag: str | None,
) -> bool:
    expression_values: dict[str, Any] = {
        ":completed": STATUS_COMPLETED,
        ":updated_at": _isoformat(now),
        ":preview": extracted_text_preview,
        ":length": extracted_text_length,
    }
    update_expression = (
        "SET #status = :completed, updatedAt = :updated_at, "
        "extractedTextPreview = :preview, extractedTextLength = :length"
    )
    if analysis is not None:
        update_expression += ", analysis = :analysis"
        expression_values[":analysis"] = analysis
    if s3_etag:
        update_expression += ", s3ETag = :s3_etag"
        expression_values[":s3_etag"] = s3_etag

    try:
        table.update_item(
            Key={"documentId": document_id},
            UpdateExpression=update_expression,
            ConditionExpression="#status = :processing",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                **expression_values,
                ":processing": STATUS_PROCESSING,
            },
        )
        return True
    except ClientError as exc:
        if _is_conditional_check_failed(exc):
            logger.info("Completion skipped because documentId=%s is no longer PROCESSING", document_id)
            return False
        raise


def _mark_failed(table: Any, document_id: str, now: datetime, reason: str, message: str) -> bool:
    try:
        table.update_item(
            Key={"documentId": document_id},
            UpdateExpression=(
                "SET #status = :failed, updatedAt = :updated_at, "
                "failureReason = :reason, errorMessage = :message"
            ),
            ConditionExpression="attribute_not_exists(#status) OR #status <> :completed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":failed": STATUS_FAILED,
                ":completed": STATUS_COMPLETED,
                ":updated_at": _isoformat(now),
                ":reason": reason,
                ":message": message,
            },
        )
        return True
    except ClientError as exc:
        if _is_conditional_check_failed(exc):
            logger.info("Failure update skipped because documentId=%s is already COMPLETED", document_id)
            return False
        raise


def _is_conditional_check_failed(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _is_retryable_client_error(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = error.get("Code", "")
    status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
    retryable_codes = {
        "InternalFailure",
        "InternalServerError",
        "LimitExceededException",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "ServiceUnavailable",
        "ServiceUnavailableException",
        "SlowDown",
        "ThrottledException",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
    }
    return code in retryable_codes or status_code >= 500


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _s3_client() -> Any:
    import boto3

    return boto3.client("s3")


def _textract_client() -> Any:
    import boto3

    return boto3.client("textract")


def _bedrock_client() -> Any:
    import boto3

    return boto3.client("bedrock-runtime")


def _document_table(table_name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(table_name)
