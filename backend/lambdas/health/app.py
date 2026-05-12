from __future__ import annotations

from typing import Any, Mapping

from shared.response import json_response


def lambda_handler(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    return json_response(200, {"status": "ok"})
