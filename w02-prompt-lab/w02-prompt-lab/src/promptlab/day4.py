"""Day 4 triage prompt comparison run."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.prompts import load, render_user
from promptlab.records import OutputRecord
from promptlab.records import append_record as append_lab_record
from promptlab.schemas import TriageOutput
from promptlab.scoring import load_triage_gold, score_triage_output
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord, append_record

CASE_IDS = tuple(f"T{index:02d}" for index in range(1, 13))
CASES_PATH = PROJECT_ROOT / "cases" / "triage.jsonl"
MAX_OUTPUT_TOKENS = 1024
RUN_DOCS_PATH = PROJECT_ROOT / "docs" / "day4-run.jsonl"
SCORE_DOCS_PATH = PROJECT_ROOT / "docs" / "day4-scores.jsonl"


class RecordingAdapter:
    def __init__(self, inner: OllamaAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.complete_calls = 0
        self.case_records: list[CallRecord] = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.complete_calls += 1
        result = self._inner.complete(request, run_id)
        self.case_records.extend(result.records)
        return result

    def reset_case(self) -> None:
        self.complete_calls = 0
        self.case_records = []


def load_cases(path: Path) -> dict[str, str]:
    cases: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload: dict[str, Any] = json.loads(line)
        case_id = str(payload["id"])
        if case_id in CASE_IDS:
            cases[case_id] = str(payload["source"])
    missing = [case_id for case_id in CASE_IDS if case_id not in cases]
    if missing:
        raise KeyError(f"Missing triage cases: {', '.join(missing)}")
    return cases


def run_prompt_version(
    *,
    adapter: RecordingAdapter,
    run_id: str,
    model_name: str,
    model_id: str,
    prompt_version: str,
    schema: type[BaseModel],
    cases: dict[str, str],
    gold: dict[str, dict[str, Any]],
    temperature: float,
) -> None:
    template = load("triage", prompt_version)
    SCORE_DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)

    for case_id in CASE_IDS:
        adapter.reset_case()
        request = CompletionRequest(
            task="triage",
            case_id=case_id,
            prompt_id="triage",
            prompt_version=prompt_version,
            system=template.system,
            user_content=render_user(template, {}, cases[case_id]),
            temperature=temperature,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        output: dict[str, Any] | None = None
        error: str | None = None
        try:
            model = complete_structured(adapter, request, schema, run_id)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            error = str(exc)
            print(
                f"triage.{prompt_version} {case_id}: failed after "
                f"{adapter.complete_calls} call(s): {exc}",
                flush=True,
            )
        else:
            output = model.model_dump()
            print(
                f"triage.{prompt_version} {case_id}: validated after "
                f"{adapter.complete_calls} call(s)",
                flush=True,
            )

        output_record = OutputRecord(
            run_id=run_id,
            task="triage",
            case_id=case_id,
            model_name=model_name,
            model_id=model_id,
            prompt_version=prompt_version,
            succeeded=output is not None,
            repairs=max(adapter.complete_calls - 1, 0),
            output=output,
            error=error,
        )
        for score in score_triage_output(
            output_record=output_record,
            gold=gold[case_id],
        ):
            append_lab_record(SCORE_DOCS_PATH, score)
        for record in adapter.case_records:
            append_record(record, run_id)


def copy_run_docs(run_id: str) -> None:
    source = Path("runs") / f"{run_id}.jsonl"
    RUN_DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_DOCS_PATH.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    settings = Settings.from_env()
    model_name = "mistral"
    model_id = settings.models[model_name].model_id
    adapter = RecordingAdapter(OllamaAdapter(model_id=model_id))
    run_id = str(uuid.uuid4())
    if SCORE_DOCS_PATH.exists():
        SCORE_DOCS_PATH.unlink()

    run_prompt_version(
        adapter=adapter,
        run_id=run_id,
        model_name=model_name,
        model_id=model_id,
        prompt_version="v1",
        schema=TriageOutput,
        cases=load_cases(CASES_PATH),
        gold=load_triage_gold(),
        temperature=0.0,
    )
    copy_run_docs(run_id)
    print(f"run_id={run_id}", flush=True)
    print(f"wrote {RUN_DOCS_PATH} and {SCORE_DOCS_PATH}", flush=True)


if __name__ == "__main__":
    main()
