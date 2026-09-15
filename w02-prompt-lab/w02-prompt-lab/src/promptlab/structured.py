from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter

_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fence = _FENCE_RE.search(stripped)
    if fence:
        return fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _parse_and_validate[T: BaseModel](text: str, schema: type[T]) -> T:
    payload: Any = json.loads(_extract_json_text(text))
    return schema.model_validate(payload)


def _build_repair_request(
    request: CompletionRequest,
    invalid_text: str,
    error: Exception,
) -> CompletionRequest:
    error_text = str(error)
    user_content = (
        "The previous response failed schema validation.\n\n"
        f"Validation error:\n{error_text}\n\n"
        "Invalid response:\n"
        f"{invalid_text}\n\n"
        "Correct only what the validation error concerns. "
        "Every evidence field must be an object with keys value, status, and citation. "
        "value must be a string, a list of strings, or null — never a nested object/dict/map. "
        "If a value was an object like "
        '{"standard_risk_customers":"every 18 months","high_risk_customers":"every 12 months"}, '
        "replace it with a list of strings such as "
        '["standard-risk customers every 18 months", "high-risk customers every 12 months"] '
        "or one equivalent string. "
        "When status is absent, set value to null and citation to null. "
        "When status is present, citation must be an exact source heading line "
        "(including any leading number such as '1. Document Control'). "
        "Do not return JSON Schema, $defs, or property descriptors. "
        "Return only a filled instance JSON object that satisfies the schema. "
        "Do not wrap the response in Markdown and do not add commentary."
    )
    return request.model_copy(update={"user_content": user_content})


def complete_structured[T: BaseModel](
    adapter: ModelAdapter,
    request: CompletionRequest,
    schema: type[T],
    run_id: str,
    max_repairs: int = 1,
) -> T:
    """Return a schema-validated completion with a bounded semantic repair loop.

    Transport retry remains inside the adapter.
    Schema/content repair belongs here.

    On validation failure, send the validation error text back to the model and
    instruct it to correct only what the error concerns. Do not perform more
    than max_repairs semantic repair attempts.
    """

    current = request
    repairs_used = 0
    last_error: Exception | None = None

    while True:
        result: CompletionResult = adapter.complete(current, run_id)
        if not result.succeeded or result.text is None:
            message = result.error_type or "model call failed without text"
            raise ValueError(message)

        try:
            return _parse_and_validate(result.text, schema)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            if repairs_used >= max_repairs:
                raise
            current = _build_repair_request(request, result.text, exc)
            repairs_used += 1

    raise RuntimeError(f"structured completion failed: {last_error}")
