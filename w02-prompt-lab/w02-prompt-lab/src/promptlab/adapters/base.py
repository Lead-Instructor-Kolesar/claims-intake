from typing import Literal, Protocol

from pydantic import BaseModel, field_validator

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

    @field_validator("task", mode="before")
    @classmethod
    def coerce_task_aliases(cls, value: object) -> object:
        aliases = {"summarize": "summarization", "extract": "extraction"}
        if isinstance(value, str):
            return aliases.get(value, value)
        return value


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
