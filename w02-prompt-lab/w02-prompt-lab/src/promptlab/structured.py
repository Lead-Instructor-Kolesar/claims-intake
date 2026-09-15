from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest, ModelAdapter

T = TypeVar("T", bound=BaseModel)


def complete_structured(
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

    raise NotImplementedError
