from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from botocore.exceptions import ClientError

from shared.bedrock import BedrockOutputError, invoke_bedrock_json
from shared.config import AppConfig, load_config
from shared.constants import STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING
from shared.textract import extract_text_from_responses

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CompletionError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.safe_message = message


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    config = load_config()
    return handle_sns_event(event, config=config)


def handle_sns_event(
    event: Mapping[str, Any],
    *,
    config: AppConfig,
    textract_client: Any | None = None,
    table: Any | None = None,
    bedrock_client: Any | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    if not config.table_name:
        raise RuntimeError("TABLE_NAME must be configured.")

    textract_client = textract_client or _textract_client()
    table = table or _document_table(config.table_name)
    if config.bedrock_model_id and bedrock_client is None:
        bedrock_client = _bedrock_client()

    results = []
    for record in event.get("Records", []):
        now = (now_factory or _utc_now)()
        result = process_sns_record(
            record,
            config=config,
            textract_client=textract_client,
            table=table,
            bedrock_client=bedrock_client,
            now=now,
        )
        results.append(result)
    return {"processed": len(results), "results": results}


def process_sns_record(
    record: Mapping[str, Any],
    *,
    config: AppConfig,
    textract_client: Any,
    table: Any,
    bedrock_client: Any | None,
    now: datetime,
) -> dict[str, Any]:
    message = _sns_message(record)
    document_id = message.get("JobTag")
    job_id = message.get("JobId")
    job_status = message.get("Status")
    if not isinstance(document_id, str) or not document_id:
        return {"status": "SKIPPED", "failureReason": "MISSING_JOB_TAG"}
    if not isinstance(job_id, str) or not job_id:
        return {"documentId": document_id, "status": "SKIPPED", "failureReason": "MISSING_JOB_ID"}

    item = _load_document(table, document_id)
    if item is None:
        logger.warning("No DynamoDB record found for documentId=%s jobId=%s", document_id, job_id)
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "MISSING_RECORD"}
    if item.get("status") == STATUS_COMPLETED:
        return {"documentId": document_id, "status": "IGNORED_COMPLETED"}
    if item.get("textractJobId") != job_id:
        return {"documentId": document_id, "status": "IGNORED_STALE_JOB"}
    if item.get("status") != STATUS_PROCESSING:
        return {"documentId": document_id, "status": "IGNORED_STATUS", "currentStatus": item.get("status")}

    try:
        if job_status != "SUCCEEDED":
            raise CompletionError("TEXTRACT_JOB_FAILED", f"Textract job ended with status {job_status}.")

        responses = _get_textract_result_pages(textract_client, job_id=job_id, max_pages=config.max_textract_pages)
        text = extract_text_from_responses(responses)
        preview = text[: config.extracted_text_preview_length]
        page_count = _page_count(responses)

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
            textract_job_id=job_id,
            now=now,
            extracted_text_preview=preview,
            extracted_text_length=len(text),
            page_count=page_count,
            analysis=analysis,
        )
        if not completed:
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_COMPLETED, "pageCount": page_count}
    except CompletionError as exc:
        if not _mark_failed_for_job(table, document_id, job_id, now, exc.reason, exc.safe_message):
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": exc.reason}
    except BedrockOutputError as exc:
        if not _mark_failed_for_job(table, document_id, job_id, now, "BEDROCK_INVALID_OUTPUT", str(exc)):
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "BEDROCK_INVALID_OUTPUT"}
    except ClientError as exc:
        if _is_retryable_client_error(exc):
            logger.warning("Retryable AWS error for documentId=%s jobId=%s: %s", document_id, job_id, exc)
            raise
        logger.exception("AWS client error while completing documentId=%s jobId=%s", document_id, job_id)
        if not _mark_failed_for_job(table, document_id, job_id, now, "AWS_CLIENT_ERROR", "AWS service call failed."):
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "AWS_CLIENT_ERROR"}
    except Exception:
        logger.exception("Completion failed for documentId=%s jobId=%s", document_id, job_id)
        if not _mark_failed_for_job(
            table,
            document_id,
            job_id,
            now,
            "PROCESSING_FAILED",
            "Document processing failed.",
        ):
            return {"documentId": document_id, "status": "IGNORED_CONCURRENT_UPDATE"}
        return {"documentId": document_id, "status": STATUS_FAILED, "failureReason": "PROCESSING_FAILED"}


def _sns_message(record: Mapping[str, Any]) -> dict[str, Any]:
    raw_message = record.get("Sns", {}).get("Message")
    if not isinstance(raw_message, str):
        raise CompletionError("INVALID_SNS_MESSAGE", "SNS message is missing.")
    parsed = json.loads(raw_message)
    if not isinstance(parsed, dict):
        raise CompletionError("INVALID_SNS_MESSAGE", "SNS message must be a JSON object.")
    return parsed


def _get_textract_result_pages(textract_client: Any, *, job_id: str, max_pages: int) -> list[Mapping[str, Any]]:
    responses: list[Mapping[str, Any]] = []
    next_token = None
    while True:
        params: dict[str, Any] = {"JobId": job_id, "MaxResults": 1000}
        if next_token:
            params["NextToken"] = next_token
        response = textract_client.get_document_text_detection(**params)
        if response.get("JobStatus") != "SUCCEEDED":
            raise CompletionError("TEXTRACT_JOB_FAILED", f"Textract result status is {response.get('JobStatus')}.")
        pages = int((response.get("DocumentMetadata") or {}).get("Pages") or 0)
        if pages > max_pages:
            raise CompletionError("DOCUMENT_TOO_MANY_PAGES", f"Document exceeds the {max_pages}-page limit.")
        responses.append(response)
        next_token = response.get("NextToken")
        if not next_token:
            return responses


def _page_count(responses: list[Mapping[str, Any]]) -> int:
    for response in responses:
        pages = int((response.get("DocumentMetadata") or {}).get("Pages") or 0)
        if pages:
            return pages
    page_numbers = [
        block.get("Page")
        for response in responses
        for block in response.get("Blocks", [])
        if isinstance(block.get("Page"), int)
    ]
    return max(page_numbers, default=0)


def _load_document(table: Any, document_id: str) -> dict[str, Any] | None:
    response = table.get_item(Key={"documentId": document_id})
    return response.get("Item")


def _mark_completed(
    table: Any,
    *,
    document_id: str,
    textract_job_id: str,
    now: datetime,
    extracted_text_preview: str,
    extracted_text_length: int,
    page_count: int,
    analysis: dict[str, Any] | None,
) -> bool:
    expression_values: dict[str, Any] = {
        ":completed": STATUS_COMPLETED,
        ":processing": STATUS_PROCESSING,
        ":job_id": textract_job_id,
        ":updated_at": _isoformat(now),
        ":preview": extracted_text_preview,
        ":length": extracted_text_length,
        ":page_count": page_count,
    }
    update_expression = (
        "SET #status = :completed, updatedAt = :updated_at, "
        "extractedTextPreview = :preview, extractedTextLength = :length, pageCount = :page_count"
    )
    if analysis is not None:
        update_expression += ", analysis = :analysis"
        expression_values[":analysis"] = analysis

    try:
        table.update_item(
            Key={"documentId": document_id},
            UpdateExpression=update_expression,
            ConditionExpression="#status = :processing AND textractJobId = :job_id",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=expression_values,
        )
        return True
    except ClientError as exc:
        if _is_conditional_check_failed(exc):
            logger.info(
                "Completion skipped because documentId=%s is no longer PROCESSING for jobId=%s",
                document_id,
                textract_job_id,
            )
            return False
        raise


def _mark_failed_for_job(
    table: Any,
    document_id: str,
    textract_job_id: str,
    now: datetime,
    reason: str,
    message: str,
) -> bool:
    try:
        table.update_item(
            Key={"documentId": document_id},
            UpdateExpression=(
                "SET #status = :failed, updatedAt = :updated_at, "
                "failureReason = :reason, errorMessage = :message"
            ),
            ConditionExpression="#status <> :completed AND textractJobId = :job_id",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":failed": STATUS_FAILED,
                ":completed": STATUS_COMPLETED,
                ":job_id": textract_job_id,
                ":updated_at": _isoformat(now),
                ":reason": reason,
                ":message": message,
            },
        )
        return True
    except ClientError as exc:
        if _is_conditional_check_failed(exc):
            logger.info("Failure update skipped for documentId=%s stale jobId=%s", document_id, textract_job_id)
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


def _textract_client() -> Any:
    import boto3

    return boto3.client("textract")


def _bedrock_client() -> Any:
    import boto3

    return boto3.client("bedrock-runtime")


def _document_table(table_name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(table_name)
