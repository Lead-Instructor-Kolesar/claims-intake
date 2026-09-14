"""Day 2 two-model summarization run through the shared adapter."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.usage import append_record

LOGICAL_MODELS = ("mistral", "qwen")
EXPECTED_CASE_IDS = tuple(f"S{index:02d}" for index in range(1, 13))
PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
TASK: Literal["summarization"] = "summarization"
MAX_OUTPUT_TOKENS = 1024
PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"
CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"


def load_summarization_cases() -> dict[str, str]:
    cases: dict[str, str] = {}
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload: dict[str, Any] = json.loads(line)
        case_id = str(payload["id"])
        if case_id in EXPECTED_CASE_IDS:
            cases[case_id] = str(payload["source"])
    missing = [case_id for case_id in EXPECTED_CASE_IDS if case_id not in cases]
    if missing:
        raise KeyError(f"Missing summarization cases: {', '.join(missing)}")
    return cases


def load_system_prompt() -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.split("<document>")[0].strip()


def build_request(
    *,
    case_id: str,
    source: str,
    system: str,
    temperature: float,
) -> CompletionRequest:
    return CompletionRequest(
        task=TASK,
        case_id=case_id,
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        system=system,
        user_content=source,
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def main() -> None:
    settings = Settings.from_env()
    cases = load_summarization_cases()
    system = load_system_prompt()
    run_id = str(uuid.uuid4())
    adapters = [
        OllamaAdapter(model_id=settings.models[name].model_id) for name in LOGICAL_MODELS
    ]

    for adapter in adapters:
        for case_id in EXPECTED_CASE_IDS:
            request = build_request(
                case_id=case_id,
                source=cases[case_id],
                system=system,
                temperature=settings.temperature,
            )
            result = adapter.complete(request, run_id)
            for record in result.records:
                append_record(record, run_id)
            print(
                f"{adapter.model_id} {case_id}: succeeded={result.succeeded} "
                f"attempts={len(result.records)} error_type={result.error_type}"
            )

    print(f"run_id={run_id}")


if __name__ == "__main__":
    main()
