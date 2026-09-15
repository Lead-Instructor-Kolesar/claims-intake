from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter


def _load_json_object(text: str | None) -> dict[str, object]:
    if text is None or not text.strip():
        raise ValueError("empty completion text failed validation")
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload: object = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("completion text failed validation: not JSON") from None
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("completion text failed validation: JSON root is not an object")
    return payload


def _repair_request(
    request: CompletionRequest,
    previous: CompletionResult,
    error: Exception,
) -> CompletionRequest:
    previous_text = previous.text or ""
    return request.model_copy(
        update={
            "user_content": (
                f"{request.user_content}\n\n"
                "The previous response failed validation.\n"
                f"Previous response:\n{previous_text}\n\n"
                f"Validation error:\n{error}\n"
                "Correct only what the validation error concerns. "
                "Return a filled JSON instance, not a JSON Schema. "
                "Use JSON true/false for booleans, never the strings True or False. "
                "Use JSON null, never the string \"null\". "
                "Keep every required field with a schema-valid value. "
                "Return only valid JSON for the requested schema."
            )
        }
    )


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

    current_request = request
    last_error: Exception | None = None
    for attempt in range(max_repairs + 1):
        result = adapter.complete(current_request, run_id)
        try:
            return schema.model_validate(_load_json_object(result.text))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= max_repairs:
                raise
            current_request = _repair_request(request, result, exc)
    assert last_error is not None
    raise last_error
