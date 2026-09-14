from __future__ import annotations

from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.structured import complete_structured


class TinySchema(BaseModel):
    value: str


class RepairingStubAdapter:
    provider = "ollama"
    model_id = "fixture-model"

    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        assert run_id == "fixture-run"
        self.calls += 1
        self.requests.append(request)

        text = '{"wrong":"shape"}' if self.calls == 1 else '{"value":"fixed"}'
        return CompletionResult(
            succeeded=True,
            text=text,
            error_type=None,
            records=[],
        )


def _request() -> CompletionRequest:
    return CompletionRequest(
        task="summarize",
        case_id="S00",
        prompt_id="summarize",
        prompt_version="v1",
        system="",
        user_content="Summarize the supplied procedure.",
        temperature=0.0,
        max_output_tokens=128,
    )


def test_complete_structured_repairs_once() -> None:
    adapter = RepairingStubAdapter()

    result = complete_structured(
        adapter,
        _request(),
        TinySchema,
        "fixture-run",
        max_repairs=1,
    )

    assert result == TinySchema(value="fixed")
    assert adapter.calls == 2


def test_repair_request_carries_validation_context() -> None:
    adapter = RepairingStubAdapter()

    complete_structured(
        adapter,
        _request(),
        TinySchema,
        "fixture-run",
        max_repairs=1,
    )

    repair_text = adapter.requests[1].user_content.lower()
    assert "validation" in repair_text or "field required" in repair_text
    assert "value" in repair_text
