from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from promptlab.records import OutputRecord, ScoreRecord, UsageRecord
from promptlab.report import write_reports


def _usage(
    *,
    model_name: str,
    prompt_version: str,
    case_id: str,
    latency_ms: float,
    prompt_tokens: int = 100,
    completion_tokens: int = 40,
    kind: str = "primary",
    attempt: int = 1,
) -> UsageRecord:
    return UsageRecord(
        run_id="day5",
        task="triage",
        case_id=case_id,
        model_name=model_name,
        model_id=f"{model_name}:id",
        prompt_version=prompt_version,
        attempt=attempt,
        kind=kind,  # type: ignore[arg-type]
        status="success",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_usd=Decimal("0"),
    )


def _output(*, model_name: str, prompt_version: str, case_id: str) -> OutputRecord:
    return OutputRecord(
        run_id="day5",
        task="triage",
        case_id=case_id,
        model_name=model_name,
        model_id=f"{model_name}:id",
        prompt_version=prompt_version,
        succeeded=True,
        repairs=0,
        output={"queue": "card_dispute", "draft_reply": "A specialist will review."},
    )


def _score(
    *,
    model_name: str,
    prompt_version: str,
    case_id: str,
    metric: str,
    numerator: int,
    denominator: int = 1,
    lower_is_better: bool = False,
) -> ScoreRecord:
    return ScoreRecord(
        run_id="day5",
        task="triage",
        case_id=case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        scorer_version="5.0.0",
        metric=metric,
        numerator=numerator,
        denominator=denominator,
        lower_is_better=lower_is_better,
    )


def test_report_day5_labels_transfer_and_reports_counts(tmp_path: Path) -> None:
    usage = [
        _usage(model_name="mistral", prompt_version="v1", case_id="T01", latency_ms=100),
        _usage(model_name="mistral", prompt_version="v1", case_id="T02", latency_ms=200),
        _usage(model_name="qwen", prompt_version="v1", case_id="T01", latency_ms=300),
        _usage(model_name="qwen", prompt_version="v1", case_id="T02", latency_ms=500),
    ]
    outputs = [
        _output(model_name="mistral", prompt_version="v1", case_id="T01"),
        _output(model_name="mistral", prompt_version="v1", case_id="T02"),
        _output(model_name="qwen", prompt_version="v1", case_id="T01"),
        _output(model_name="qwen", prompt_version="v1", case_id="T02"),
    ]
    scores = [
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T01",
            metric="queue_accuracy",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T02",
            metric="queue_accuracy",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T01",
            metric="escalation_accuracy",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T02",
            metric="escalation_accuracy",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T01",
            metric="missed_escalation",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T02",
            metric="missed_escalation",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T01",
            metric="human_boundary_compliance",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T02",
            metric="human_boundary_compliance",
            numerator=1,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T01",
            metric="pii_leakage",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="mistral",
            prompt_version="v1",
            case_id="T02",
            metric="pii_leakage",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T01",
            metric="queue_accuracy",
            numerator=0,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T02",
            metric="queue_accuracy",
            numerator=1,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T01",
            metric="escalation_accuracy",
            numerator=1,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T02",
            metric="escalation_accuracy",
            numerator=1,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T01",
            metric="missed_escalation",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T02",
            metric="missed_escalation",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T01",
            metric="human_boundary_compliance",
            numerator=1,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T02",
            metric="human_boundary_compliance",
            numerator=1,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T01",
            metric="pii_leakage",
            numerator=0,
            lower_is_better=True,
        ),
        _score(
            model_name="qwen",
            prompt_version="v1",
            case_id="T02",
            metric="pii_leakage",
            numerator=0,
            lower_is_better=True,
        ),
    ]

    report = tmp_path / "comparison.md"
    decision = tmp_path / "model-decision.md"
    write_reports(
        run_id="day5",
        models=["mistral", "qwen"],
        usage=usage,
        outputs=outputs,
        scores=scores,
        report_path=report,
        decision_path=decision,
    )
    text = report.read_text(encoding="utf-8")
    decision_text = decision.read_text(encoding="utf-8")

    assert "triage.v1" in text
    assert "(transfer)" in text
    assert "queue_accuracy: 2/2" in text
    assert "%" not in text.split("## Limits")[0]
    assert "Median latency" in text
    assert "Max latency" in text
    assert "n |" in text or "| n |" in text
    assert "$0.00" in text
    assert "12" in text.split("## Limits")[1]
    assert "mistral" in text.split("## Human boundary")[1]
    assert "qwen" in text.split("## Human boundary")[1]
    assert "Recommendation" in text or "recommendation" in text.lower()
    assert "triage" in decision_text
    assert "mistral" in decision_text
    assert "v1" in decision_text
    assert "reopen" in decision_text.lower()
