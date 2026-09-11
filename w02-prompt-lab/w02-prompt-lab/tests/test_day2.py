from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from promptlab import day2
from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.config import Settings
from promptlab.usage import CallRecord


def test_load_cases_rejects_a_non_object_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text('{"id":"S01","task":"summarization","source":"x"}\n[1,2]\n', encoding="utf-8")
    monkeypatch.setattr(day2, "CASES_PATH", path)

    with pytest.raises(ValueError, match="non-object"):
        day2.load_cases()


def test_load_cases_returns_all_twelve_in_file_order() -> None:
    cases = day2.load_cases()

    assert [case["id"] for case in cases] == [f"S{index:02d}" for index in range(1, 13)]
    assert {case["task"] for case in cases} == {"summarization"}
    assert all(case["source"] for case in cases)


def test_split_prompt_without_document_marker_puts_all_text_in_user() -> None:
    system, user_content = day2.split_prompt("Prefix {document_text}", "BODY")

    assert system == ""
    assert user_content == "Prefix BODY"


def test_split_prompt_uses_the_same_baseline_for_every_case() -> None:
    template = day2.PROMPT_PATH.read_text(encoding="utf-8")
    system, user_content = day2.split_prompt(template, "CASE-BODY")

    assert "{document_text}" not in system
    assert "{document_text}" not in user_content
    assert "CASE-BODY" in user_content
    assert "CASE-BODY" not in system
    assert user_content.startswith("<document>")
    assert system
    assert day2.split_prompt(template, "CASE-BODY") == (system, user_content)


def test_build_request_keeps_shared_fields_off_the_model() -> None:
    case = {"id": "S04", "task": "summarization", "source": "doc"}
    built = day2.build_request(case, "system", "user", 0.0)

    assert built == CompletionRequest(
        task="summarization",
        case_id="S04",
        prompt_id="baseline",
        prompt_version="v0",
        system="system",
        user_content="user",
        temperature=0.0,
        max_output_tokens=day2.MAX_OUTPUT_TOKENS,
    )


def test_summarize_reports_counts_tokens_and_latency() -> None:
    records = [
        _record("model-a", "S01", 100, 3, 10),
        _record("model-a", "S02", 120, 5, 30, error_type="TruncatedResponseError"),
        _record("model-a", "S03", 80, 1, 20),
        _record("model-b", "S01", 90, 8, 40),
        _record("model-b", "S02", 110, 6, 50),
    ]

    text = day2.summarize(records)

    assert "successes: 2" in text
    assert "attempts: 3" in text
    assert "input tokens: 300" in text
    assert "output tokens: 9" in text
    assert "median latency: 20 ms" in text
    assert "max latency: 30 ms" in text
    assert "attempts: 2" in text
    assert "input tokens: 200" in text
    assert "output tokens: 14" in text
    assert "median latency: 45 ms" in text
    assert "max latency: 50 ms" in text
    assert "cost_usd is 0.0" in text
    assert "model-a" in text
    assert "model-b" in text
    assert "1.6 times the output tokens" in text
    assert "2.2 times the median latency" in text
    assert "truncated attempts" in text
    assert "\u2014" not in text
    assert "$" not in text


def test_summarize_handles_empty_and_single_model_runs() -> None:
    assert day2.summarize([]) == "No model calls were recorded.\n"

    one = day2.summarize([_record("only-model", "S01", 10, 2, 5)])
    assert "only-model recorded 1 successes in 1 attempts" in one
    assert "A second configured model is needed" in one


def test_summarize_notes_nonzero_cost_without_inventing_a_price() -> None:
    record = _record("model-a", "S01", 10, 2, 5)
    record = record.model_copy(update={"cost_usd": 0.01})
    text = day2.summarize([record, _record("model-b", "S01", 8, 0, 9)])

    assert "were not all 0.0" in text
    assert "does not invent a price" in text
    assert "n/a times the output tokens" in text


def test_main_runs_both_models_with_identical_request_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings.from_env()
    captured: list[tuple[str, CompletionRequest, str]] = []
    appended: list[CallRecord] = []

    class FakeAdapter:
        def __init__(self, model_id: str, base_url: str) -> None:
            self.provider = "ollama"
            self.model_id = model_id
            self.base_url = base_url

        def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
            captured.append((self.model_id, request, run_id))
            record = _record(
                self.model_id,
                request.case_id,
                input_tokens=10,
                output_tokens=2,
                latency_ms=15,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                run_id=run_id,
            )
            return CompletionResult(
                succeeded=True,
                text="ok",
                error_type=None,
                records=[record],
            )

    def fake_append(record: CallRecord, run_id: str) -> None:
        assert record.run_id == run_id
        appended.append(record)

    monkeypatch.setattr(day2, "OllamaAdapter", FakeAdapter)
    monkeypatch.setattr(day2, "append_record", fake_append)
    monkeypatch.setattr(day2, "uuid4", lambda: UUID("00000000-0000-4000-8000-0000000000b2"))
    monkeypatch.setattr(day2, "DOCS_RUN_PATH", tmp_path / "day2-run.jsonl")
    monkeypatch.setattr(day2, "DOCS_COMPARISON_PATH", tmp_path / "day2-comparison.md")

    day2.main()

    model_ids = [config.model_id for config in settings.models.values()]
    assert [item[0] for item in captured[:12]] == [model_ids[0]] * 12
    assert [item[0] for item in captured[12:]] == [model_ids[1]] * 12
    assert [item[1].case_id for item in captured[:12]] == [f"S{i:02d}" for i in range(1, 13)]
    assert {item[2] for item in captured} == {"00000000-0000-4000-8000-0000000000b2"}

    by_case: dict[str, list[CompletionRequest]] = {}
    for _model_id, request, _run_id in captured:
        by_case.setdefault(request.case_id, []).append(request)

    shared = (
        "task",
        "case_id",
        "prompt_id",
        "prompt_version",
        "system",
        "user_content",
        "temperature",
        "max_output_tokens",
    )
    assert set(by_case) == {f"S{i:02d}" for i in range(1, 13)}
    for requests in by_case.values():
        assert len(requests) == 2
        left, right = requests
        for field in shared:
            assert getattr(left, field) == getattr(right, field)
        assert left.temperature == settings.temperature
        assert left.max_output_tokens == day2.MAX_OUTPUT_TOKENS
        assert left.prompt_id == "baseline"
        assert left.prompt_version == "v0"
        assert left.task == "summarization"

    assert len(appended) == 24
    run_lines = (tmp_path / "day2-run.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(run_lines) == 24
    parsed = [CallRecord.model_validate_json(line) for line in run_lines]
    assert {record.provider for record in parsed} == {"ollama"}
    assert {record.model_id for record in parsed} == set(model_ids)
    comparison = (tmp_path / "day2-comparison.md").read_text(encoding="utf-8")
    assert "successes: 12" in comparison
    assert "attempts: 12" in comparison
    assert "cost_usd is 0.0" in comparison
    assert "\u2014" not in comparison


def test_main_skips_a_result_with_no_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class EmptyAdapter:
        def __init__(self, model_id: str, base_url: str) -> None:
            self.model_id = model_id

        def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
            return CompletionResult(succeeded=False, text=None, error_type=None, records=[])

    monkeypatch.setattr(day2, "OllamaAdapter", EmptyAdapter)
    monkeypatch.setattr(day2, "append_record", lambda *_args: None)
    monkeypatch.setattr(day2, "DOCS_RUN_PATH", tmp_path / "day2-run.jsonl")
    monkeypatch.setattr(day2, "DOCS_COMPARISON_PATH", tmp_path / "day2-comparison.md")

    day2.main()
    out = capsys.readouterr().out
    assert "no attempt recorded" in out
    assert (tmp_path / "day2-run.jsonl").read_text(encoding="utf-8") == ""
    assert "No model calls were recorded" in (tmp_path / "day2-comparison.md").read_text(
        encoding="utf-8"
    )


def test_model_identifiers_and_ollama_fields_stay_inside_the_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    model_ids = ("mistral:7b", "qwen3:8b")
    field_names = ("prompt_eval_count", "eval_count", "done_reason", "num_predict")
    outside = [
        root / "src/promptlab/day2.py",
        root / "src/promptlab/adapters/base.py",
        root / "src/promptlab/adapters/__init__.py",
    ]
    adapter = (root / "src/promptlab/adapters/ollama.py").read_text(encoding="utf-8")

    for name in ("prompt_eval_count", "eval_count", "done_reason"):
        assert name in adapter
    for token in model_ids:
        assert token not in adapter
    for path in outside:
        text = path.read_text(encoding="utf-8")
        for token in field_names + model_ids:
            assert token not in text, f"{token} leaked into {path.name}"
    assert "httpx" not in (root / "src/promptlab/day2.py").read_text(encoding="utf-8")
    assert "api/generate" not in (root / "src/promptlab/day2.py").read_text(encoding="utf-8")


def test_day2_run_evidence_matches_call_record() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "day2-run.jsonl"
    records = [
        CallRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    settings = Settings.from_env()
    model_ids = {config.model_id for config in settings.models.values()}
    cases = {f"S{index:02d}" for index in range(1, 13)}

    assert {record.run_id for record in records} == {records[0].run_id}
    assert {record.provider for record in records} == {"ollama"}
    assert {record.model_id for record in records} == model_ids
    assert {record.task for record in records} == {"summarization"}
    assert {record.case_id for record in records} == cases
    assert {record.prompt_id for record in records} == {"baseline"}
    assert {record.prompt_version for record in records} == {"v0"}
    assert {record.temperature for record in records} == {settings.temperature}
    assert {record.max_output_tokens for record in records} == {day2.MAX_OUTPUT_TOKENS}
    assert all(record.cost_usd == 0.0 for record in records)
    assert all(record.timestamp.tzinfo is not None for record in records)
    assert all(record.attempt >= 1 for record in records)
    by_case: dict[str, list[CallRecord]] = {}
    for record in records:
        by_case.setdefault(record.case_id, []).append(record)
    for group in by_case.values():
        models = {item.model_id for item in group}
        assert models == model_ids
        fields = (
            "task",
            "case_id",
            "prompt_id",
            "prompt_version",
            "temperature",
            "max_output_tokens",
        )
        first = group[0]
        for item in group[1:]:
            for field in fields:
                assert getattr(item, field) == getattr(first, field)


def _record(
    model_id: str,
    case_id: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    *,
    error_type: str | None = None,
    temperature: float = 0.0,
    max_output_tokens: int = 256,
    run_id: str = "run-day2",
) -> CallRecord:
    return CallRecord(
        record_id="00000000-0000-4000-8000-000000000001",
        run_id=run_id,
        timestamp=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        provider="ollama",
        model_id=model_id,
        task="summarization",
        case_id=case_id,
        prompt_id="baseline",
        prompt_version="v0",
        attempt=1,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=None,
        latency_ms=latency_ms,
        cost_usd=0.0,
        stop_reason="length" if error_type == "TruncatedResponseError" else "stop",
        error_type=error_type,
        response_text=None if error_type else "summary",
    )
