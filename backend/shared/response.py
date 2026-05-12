from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any, Mapping


class BadRequestError(ValueError):
    """Raised when an API Gateway request cannot be parsed or validated."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_response(status_code: int, body: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=_json_default),
    }


def parse_json_body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw_body = event.get("body")
    if raw_body in (None, ""):
        raise BadRequestError("Request body is required.")

    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise BadRequestError("Request body must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise BadRequestError("Request body must be a JSON object.")
    return parsed
