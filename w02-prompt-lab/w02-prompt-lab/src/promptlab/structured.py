from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter


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
    last_error: Exception | None = None
    for repair_index in range(max_repairs + 1):
        result = adapter.complete(current, run_id)
        try:
            return parse_and_validate(result, schema)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            if repair_index >= max_repairs:
                break
            current = request.model_copy(
                update={
                    "user_content": repair_user_content(
                        original=request.user_content,
                        previous_text=result.text,
                        error=exc,
                    )
                }
            )
    assert last_error is not None
    raise last_error


def parse_and_validate[T: BaseModel](result: CompletionResult, schema: type[T]) -> T:
    if not result.succeeded or result.text is None or not result.text.strip():
        raise ValueError("Model call did not return text that can be validated")
    payload = parse_json_text(result.text)
    return schema.model_validate(payload)


def parse_json_text(text: str) -> object:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response was not valid JSON: {exc}") from exc


def repair_user_content(
    *,
    original: str,
    previous_text: str | None,
    error: Exception,
) -> str:
    previous = previous_text or ""
    return (
        f"{original}\n\n"
        "The previous JSON failed validation.\n"
        f"Validation error:\n{error}\n\n"
        "Correct only what the validation error concerns. "
        "Return only a JSON object that satisfies the schema.\n\n"
        f"Previous output:\n{previous}"
    )
