from __future__ import annotations

from typing import Any, Mapping

from shared.config import AppConfig, load_config
from shared.constants import STATUS_COMPLETED, STATUS_FAILED
from shared.response import json_response


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    config = load_config()
    try:
        return handle_get_document(event, config=config)
    except Exception:
        return json_response(500, {"message": "Internal server error."})


def handle_get_document(
    event: Mapping[str, Any],
    *,
    config: AppConfig,
    table: Any | None = None,
) -> dict[str, Any]:
    document_id = (event.get("pathParameters") or {}).get("documentId")
    if not document_id:
        return json_response(400, {"message": "documentId path parameter is required."})
    if not config.table_name:
        raise RuntimeError("TABLE_NAME must be configured.")

    table = table or _document_table(config.table_name)
    response = table.get_item(Key={"documentId": document_id})
    item = response.get("Item")
    if not item:
        return json_response(404, {"message": "Document not found."})
    return json_response(200, _serialize_document(item))


def _serialize_document(item: Mapping[str, Any]) -> dict[str, Any]:
    status = item.get("status")
    body: dict[str, Any] = {
        "documentId": item.get("documentId"),
        "status": status,
    }
    if status == STATUS_COMPLETED:
        _copy_if_present(item, body, ("documentType", "filename", "extractedTextPreview"))
        if "analysis" in item:
            body["analysis"] = item["analysis"]
    elif status == STATUS_FAILED:
        _copy_if_present(item, body, ("documentType", "filename", "failureReason", "errorMessage"))
    return body


def _copy_if_present(source: Mapping[str, Any], target: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def _document_table(table_name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(table_name)
