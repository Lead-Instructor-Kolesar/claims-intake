from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from promptlab.config import PROJECT_ROOT
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.schemas import TriageOutput, TriageOutputWithAnalysis
from promptlab.scoring import _boundary_holds
from promptlab.usage import CallRecord

PROMPT_DIR = PROJECT_ROOT / "src" / "prompts"
TRIAGE_V1 = PROMPT_DIR / "triage.v1.md"
TRIAGE_V2 = PROMPT_DIR / "triage.v2.md"


def test_triage_prompts_live_under_src_prompts() -> None:
    assert TRIAGE_V1.is_file()
    assert TRIAGE_V2.is_file()
    assert "promptlab" not in TRIAGE_V1.parts[-3:]
    assert TRIAGE_V1.parent == PROMPT_DIR
    assert not (PROJECT_ROOT / "src" / "promptlab" / "triage.v1.md").exists()


def test_triage_prompts_are_layered() -> None:
    for path in (TRIAGE_V1, TRIAGE_V2):
        text = path.read_text(encoding="utf-8")
        assert text.index("## System") < text.index("## User")
        assert "<customer_message>" in text
        assert "</customer_message>" in text
        assert "{document_text}" in text
        assert "{schema_description}" in text


def test_triage_v1_does_not_request_analysis() -> None:
    text = TRIAGE_V1.read_text(encoding="utf-8").lower()
    assert "analysis" not in text
    assert "triageoutput" in text.replace(" ", "")


def test_triage_v2_requests_analysis_without_replacing_rationale() -> None:
    text = TRIAGE_V2.read_text(encoding="utf-8").lower()
    assert "analysis" in text
    assert "rationale" in text
    assert "triageoutputwithanalysis" in text.replace(" ", "").replace("_", "")


def test_build_request_uses_triage_task() -> None:
    from promptlab.day4 import build_request

    request = build_request(
        case_id="T01",
        prompt_version="v1",
        system="standing",
        user_content="hello",
        temperature=0.0,
    )
    assert request.task == "triage"
    assert request.prompt_id == "triage"
    assert request.prompt_version == "v1"
    assert request.temperature == 0.0
    assert request.max_output_tokens == 1024


def test_render_case_uses_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import promptlab.prompts as prompts
    from promptlab.day4 import render_case

    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "triage.v1.md").write_text(
        "## System\nSchema:\n{schema_description}\n\n"
        "## User\n<customer_message>\n{document_text}\n</customer_message>\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(prompts, "PROMPT_DIR", prompt_dir)

    system, user_content = render_case("v1", "please help", TriageOutput)
    assert "please help" in user_content
    assert "<customer_message>" in user_content
    assert "queue" in system
    assert "{schema_description}" not in system
    assert "{document_text}" not in user_content


def test_changed_queue_count_compares_versions() -> None:
    from promptlab.day4 import changed_queue_count

    outputs = [
        _output("T01", "v1", "card_dispute"),
        _output("T01", "v2", "fraud_report"),
        _output("T02", "v1", "fraud_report"),
        _output("T02", "v2", "fraud_report"),
    ]
    assert changed_queue_count(outputs) == 1


def test_format_notes_uses_counts_and_zero_cost() -> None:
    from promptlab.day4 import format_notes

    notes = format_notes(
        run_id="run-1",
        model_id="mistral:7b",
        outputs=[
            _output("T01", "v1", "card_dispute"),
            _output("T01", "v2", "card_dispute"),
        ],
        scores=[
            *_scores("T01", "v1", queue=1, escalation=1, missed=0, unnecessary=0, boundary=1),
            *_scores("T01", "v2", queue=1, escalation=1, missed=0, unnecessary=0, boundary=1),
        ],
        calls=[
            _call("T01", "v1", output_tokens=40, latency_ms=100),
            _call("T01", "v2", output_tokens=55, latency_ms=120),
        ],
    )
    assert "queue correct: 1/1" in notes
    assert "$0.00" in notes
    assert "run-1" in notes
    assert "mistral:7b" in notes
    assert "observation count: 2" in notes
    assert "T01: v1=40 v2=55" in notes


def test_day4_does_not_open_prompt_files_directly() -> None:
    source = Path("src/promptlab/day4.py").read_text(encoding="utf-8")
    assert "triage.v1.md" not in source
    assert "triage.v2.md" not in source
    assert "load(" in source


def test_committed_day4_drafts_pass_human_boundary() -> None:
    path = PROJECT_ROOT / "docs" / "day4-run.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 24
    assert len({row["run_id"] for row in rows}) == 1
    for row in rows:
        schema = TriageOutput if row["prompt_version"] == "v1" else TriageOutputWithAnalysis
        output = schema.model_validate(row["output"])
        assert _boundary_holds(output), row["case_id"] + " " + row["prompt_version"]
        if row["prompt_version"] == "v1":
            assert "analysis" not in row["output"]
        else:
            assert isinstance(output, TriageOutputWithAnalysis)
            assert output.analysis


def test_committed_day4_notes_use_counts_and_zero_cost() -> None:
    notes = (PROJECT_ROOT / "docs" / "day4-notes.md").read_text(encoding="utf-8")
    assert "queue correct:" in notes
    assert "human-boundary passes: 12/12" in notes
    assert "Provider/API cost: $0.00" in notes
    assert "output-token difference" in notes
    assert "changed-queue count:" in notes
    assert "observation count:" in notes
    assert "Temperature: 0.0" in notes
    assert "mistral:7b" in notes


def _output(case_id: str, prompt_version: str, queue: str) -> OutputRecord:
    return OutputRecord(
        run_id="run-1",
        task="triage",
        case_id=case_id,
        model_name="mistral",
        model_id="mistral:7b",
        prompt_version=prompt_version,
        succeeded=True,
        repairs=0,
        output={
            "queue": queue,
            "escalation_required": False,
            "confidence": 0.9,
            "rationale": "x",
            "draft_reply": "A specialist will review your request.",
            "human_review_required": True,
            "customer_outcome": None,
        },
        error=None,
    )


def _scores(
    case_id: str,
    prompt_version: str,
    *,
    queue: int,
    escalation: int,
    missed: int,
    unnecessary: int,
    boundary: int,
) -> list[ScoreRecord]:
    pairs = [
        ("queue_accuracy", queue, False),
        ("escalation_accuracy", escalation, False),
        ("missed_escalation", missed, True),
        ("unnecessary_escalation", unnecessary, True),
        ("human_boundary_compliance", boundary, False),
    ]
    return [
        ScoreRecord(
            run_id="run-1",
            task="triage",
            case_id=case_id,
            model_name="mistral",
            prompt_version=prompt_version,
            scorer_version="4.0.0",
            metric=metric,
            numerator=value,
            denominator=1,
            lower_is_better=lower,
        )
        for metric, value, lower in pairs
    ]


def _call(case_id: str, prompt_version: str, *, output_tokens: int, latency_ms: int) -> CallRecord:
    return CallRecord(
        record_id=f"{case_id}-{prompt_version}",
        run_id="run-1",
        timestamp=datetime(2026, 9, 15, tzinfo=UTC),
        provider="ollama",
        model_id="mistral:7b",
        task="triage",
        case_id=case_id,
        prompt_id="triage",
        prompt_version=prompt_version,
        attempt=1,
        temperature=0.0,
        max_output_tokens=1024,
        input_tokens=10,
        output_tokens=output_tokens,
        cached_input_tokens=None,
        latency_ms=latency_ms,
        cost_usd=0.0,
        stop_reason="stop",
        error_type=None,
        response_text="{}",
    )
