from __future__ import annotations

from typing import Any, Mapping


def extract_lines(textract_response: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for block in textract_response.get("Blocks", []):
        if block.get("BlockType") == "LINE" and block.get("Text"):
            lines.append(block["Text"])
    return lines


def extract_text(textract_response: Mapping[str, Any]) -> str:
    return "\n".join(extract_lines(textract_response))


def extract_text_from_responses(textract_responses: list[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for response in textract_responses:
        lines.extend(extract_lines(response))
    return "\n".join(lines)
