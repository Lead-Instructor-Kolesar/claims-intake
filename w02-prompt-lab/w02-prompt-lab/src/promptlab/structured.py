from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, ModelAdapter
from promptlab.usage import CallRecord


@dataclass
class StructuredCallTrace:
    """Observation of one structured completion, including every adapter call."""

    records: list[CallRecord] = field(default_factory=list)
    repairs: int = 0
    first_error: str | None = None
    final_error: str | None = None
    repair_record_ids: list[str] = field(default_factory=list)


class StructuredCompletionError(RuntimeError):
    """Raised when no schema-valid object could be produced."""

    def __init__(self, message: str, trace: StructuredCallTrace) -> None:
        super().__init__(message)
        self.trace = trace


def complete_structured[T: BaseModel](
    adapter: ModelAdapter,
    request: CompletionRequest,
    schema: type[T],
    run_id: str,
    max_repairs: int = 1,
    *,
    trace: StructuredCallTrace | None = None,
) -> T:
    """Return a schema-validated completion with a bounded semantic repair loop.

    Transport retry remains inside the adapter.
    Schema/content repair belongs here.

    On validation failure, send the validation error text back to the model and
    instruct it to correct only what the error concerns. Do not perform more
    than max_repairs semantic repair attempts.
    """
    if trace is None:
        trace = StructuredCallTrace()

    result = adapter.complete(request, run_id)
    trace.records.extend(result.records)
    raw_text = result.text
    if not result.succeeded or raw_text is None:
        message = f"adapter call failed before producing text (error_type={result.error_type})"
        trace.final_error = message
        raise StructuredCompletionError(message, trace)

    outcome = _parse_and_validate(schema, raw_text)
    if not isinstance(outcome, str):
        trace.final_error = None
        return outcome

    trace.first_error = outcome
    trace.final_error = outcome

    for attempt in range(1, max_repairs + 1):
        repair_request = _repair_request(request, previous_text=raw_text, error_text=outcome)
        repair_result = adapter.complete(repair_request, run_id)
        trace.repairs = attempt
        trace.records.extend(repair_result.records)
        trace.repair_record_ids.extend(call.record_id for call in repair_result.records)
        repair_text = repair_result.text
        if not repair_result.succeeded or repair_text is None:
            message = (
                "repair adapter call failed before producing text "
                f"(error_type={repair_result.error_type})"
            )
            trace.final_error = message
            raise StructuredCompletionError(message, trace)

        repair_outcome = _parse_and_validate(schema, repair_text)
        if not isinstance(repair_outcome, str):
            trace.final_error = None
            return repair_outcome
        trace.final_error = repair_outcome
    raise StructuredCompletionError(
        f"no schema-valid response after {trace.repairs} repair attempt(s): {trace.final_error}",
        trace,
    )


def _parse_and_validate[T: BaseModel](schema: type[T], text: str) -> T | str:
    """Return the validated model instance, or an error string describing the failure."""
    payload = _extract_json_object(text)
    if payload is None:
        return "The model response was not valid JSON, so schema validation could not run."
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        return str(exc)


def _extract_json_object(text: str) -> dict[str, object] | None:
    """Parse the text as a JSON object, tolerating code fences and surrounding prose."""
    for candidate in _json_candidates(text):
        try:
            parsed: object = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _json_candidates(text: str) -> Iterator[str]:
    """Yield progressively more forgiving candidate strings for JSON parsing."""
    stripped = text.strip()
    yield stripped
    without_fences = _strip_code_fences(stripped)
    yield without_fences
    braced = _brace_substring(without_fences)
    if braced is not None:
        yield braced


def _strip_code_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].lstrip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _brace_substring(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    return text[start : end + 1]


def _repair_request(
    request: CompletionRequest,
    previous_text: str,
    error_text: str,
) -> CompletionRequest:
    """Re-send the original prompt with the failed response and validation error."""
    user_content = (
        f"{request.user_content}\n\n"
        "Your previous response did not match the required output schema.\n\n"
        "Previous response:\n"
        f"{previous_text}\n\n"
        "Validation error:\n"
        f"{error_text}\n\n"
        "Do not return the schema description or any schema text; every field "
        "must hold concrete values, not type declarations. The top level of the "
        "JSON object must contain exactly the expected field names, with no "
        "wrapper key. "
        "Correct only what the validation error concerns and return the full corrected "
        "JSON object only, with no Markdown fencing and no commentary."
    )
    return request.model_copy(update={"user_content": user_content})
