"""Structured output with a capped repair. Week 2 reference implementation.

This sits above the adapter. Transport retry is the adapter's concern and
semantic repair is this module's, and keeping them in separate layers is why the
adapter never learns what a schema is.

A validation failure is data. Resending the identical request produces the
identical failure at twice the price, so a repair carries the validation error
text and instructs correction of only what the error concerns.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.usage import CallRecord

M = TypeVar("M", bound=BaseModel)

_REPAIR_TEMPLATE = """Your previous response did not validate against the required \
output contract.

The validation error was:
{error}

Return the corrected object. Change only what this error concerns and leave every \
other field exactly as you returned it. Return the object and nothing else.

Your previous response was:
{previous}"""


class StructuredOutcome(BaseModel):
    """The result of one structured call, including a failure.

    A failure is recorded rather than discarded, because a run that hides its
    validation failures appears cleaner than it was.
    """

    model_config = {"arbitrary_types_allowed": True}

    succeeded: bool
    parsed: BaseModel | None
    repairs_used: int
    error_type: str | None
    error_detail: str | None
    records: list[CallRecord]


def complete_structured(
    adapter: ModelAdapter,
    request: CompletionRequest,
    schema: type[M],
    run_id: str,
    max_repairs: int = 1,
) -> StructuredOutcome:
    """Call the adapter and parse the response into `schema`, repairing once.

    Every attempt, including repairs and failures, appends a CallRecord through
    the adapter, so the true cost of a case includes what the repair cost.
    """
    records: list[CallRecord] = []
    attempt_request = request
    last_text: str | None = None
    last_error: str | None = None

    for repairs_used in range(max_repairs + 1):
        result: CompletionResult = adapter.complete(attempt_request, run_id)
        records.extend(result.records)

        if not result.succeeded or result.text is None:
            return StructuredOutcome(
                succeeded=False,
                parsed=None,
                repairs_used=repairs_used,
                error_type=result.error_type or "EmptyResponse",
                error_detail=None,
                records=records,
            )

        last_text = result.text
        try:
            return StructuredOutcome(
                succeeded=True,
                parsed=schema.model_validate_json(_strip_fences(result.text)),
                repairs_used=repairs_used,
                error_type=None,
                error_detail=None,
                records=records,
            )
        except ValidationError as exc:
            last_error = str(exc)
            if repairs_used == max_repairs:
                break
            attempt_request = request.model_copy(
                update={
                    "user_content": _REPAIR_TEMPLATE.format(
                        error=last_error, previous=last_text
                    )
                }
            )

    return StructuredOutcome(
        succeeded=False,
        parsed=None,
        repairs_used=max_repairs,
        error_type="ValidationError",
        error_detail=last_error,
        records=records,
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
