from __future__ import annotations

import json
from typing import Any, Mapping

from shared.prompts import EXPECTED_SCHEMA_KEYS, build_prompt


class BedrockOutputError(ValueError):
    """Raised when Bedrock returns invalid or unexpected JSON."""


def invoke_bedrock_json(
    bedrock_client: Any,
    *,
    model_id: str,
    document_type: str,
    extracted_text: str,
    text_limit: int,
) -> dict[str, Any]:
    prompt = build_prompt(document_type, extracted_text, text_limit=text_limit)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1200,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
    }

    response = bedrock_client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = _read_response_body(response)
    text = _extract_text_from_bedrock_payload(payload)
    parsed = parse_model_json(text)
    validate_model_json(document_type, parsed)
    return parsed


def parse_model_json(text: str) -> dict[str, Any]:
    parsed = _decode_json_object(text)
    if not isinstance(parsed, dict):
        raise BedrockOutputError("Bedrock response JSON must be an object.")
    return parsed


def _decode_json_object(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return parsed

    raise BedrockOutputError("Bedrock response was not valid JSON.")


def validate_model_json(document_type: str, payload: Mapping[str, Any]) -> None:
    expected_keys = EXPECTED_SCHEMA_KEYS[document_type]
    missing = sorted(expected_keys - set(payload.keys()))
    if missing:
        raise BedrockOutputError(f"Bedrock response is missing keys: {', '.join(missing)}.")

    if document_type == "resume":
        score = payload.get("atsScore")
        if score is not None and (not isinstance(score, (int, float)) or score < 0 or score > 100):
            raise BedrockOutputError("atsScore must be a number between 0 and 100.")


def _read_response_body(response: Mapping[str, Any]) -> dict[str, Any]:
    raw_body = response["body"].read()
    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8")
    return json.loads(raw_body)


def _extract_text_from_bedrock_payload(payload: Mapping[str, Any]) -> str:
    content = payload.get("content", [])
    if content and isinstance(content, list):
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    if isinstance(payload.get("completion"), str):
        return payload["completion"]
    raise BedrockOutputError("Bedrock response did not include text content.")
