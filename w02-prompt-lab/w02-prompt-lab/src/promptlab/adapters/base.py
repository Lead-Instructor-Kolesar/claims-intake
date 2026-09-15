from typing import Literal, Protocol

from pydantic import BaseModel

from promptlab.usage import CallRecord


class CompletionRequest(BaseModel):
    task: Literal["triage", "summarization", "extraction"]
    case_id: str
    prompt_id: str
    prompt_version: str
    system: str
    user_content: str
    temperature: float
    max_output_tokens: int


class CompletionResult(BaseModel):
    succeeded: bool
    text: str | None
    error_type: str | None
    records: list[CallRecord]


class ModelAdapter(Protocol):
    provider: str
    model_id: str

    def complete(
        self,
        request: CompletionRequest,
        run_id: str,
    ) -> CompletionResult: ...
