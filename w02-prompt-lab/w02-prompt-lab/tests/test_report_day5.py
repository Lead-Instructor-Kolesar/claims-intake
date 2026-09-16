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
    task: str = "triage",
) -> UsageRecord:
    return UsageRecord(
        run_id="day5",
        task=task,  # type: ignore[arg-type]
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


def _output(
    *,
    model_name: str,
    prompt_version: str,
    case_id: str,
    succeeded: bool = True,
    task: str = "triage",
) -> OutputRecord:
    return OutputRecord(
        run_id="day5",
        task=task,  # type: ignore[arg-type]
        case_id=case_id,
        model_name=model_name,
        model_id=f"{model_name}:id",
        prompt_version=prompt_version,
        succeeded=succeeded,
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
    task: str = "triage",
) -> ScoreRecord:
    return ScoreRecord(
        run_id="day5",
        task=task,  # type: ignore[arg-type]
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
    assert "selected model: mistral" in decision_text
    assert "no generation failures" in decision_text


def _triage_pair(
    *,
    model_name: str,
    queue: tuple[int, int],
    escalation: tuple[int, int] = (1, 1),
    missed: tuple[int, int] = (0, 0),
    boundary: tuple[int, int] = (1, 1),
    pii: tuple[int, int] = (0, 0),
    latency_ms: tuple[float, float] = (100.0, 200.0),
    completion_tokens: int = 40,
) -> tuple[list[UsageRecord], list[OutputRecord], list[ScoreRecord]]:
    usage = [
        _usage(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            latency_ms=latency_ms[0],
            completion_tokens=completion_tokens,
        ),
        _usage(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            latency_ms=latency_ms[1],
            completion_tokens=completion_tokens,
        ),
    ]
    outputs = [
        _output(model_name=model_name, prompt_version="v1", case_id="T01"),
        _output(model_name=model_name, prompt_version="v1", case_id="T02"),
    ]
    scores = [
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            metric="queue_accuracy",
            numerator=queue[0],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            metric="queue_accuracy",
            numerator=queue[1],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            metric="escalation_accuracy",
            numerator=escalation[0],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            metric="escalation_accuracy",
            numerator=escalation[1],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            metric="missed_escalation",
            numerator=missed[0],
            lower_is_better=True,
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            metric="missed_escalation",
            numerator=missed[1],
            lower_is_better=True,
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            metric="human_boundary_compliance",
            numerator=boundary[0],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            metric="human_boundary_compliance",
            numerator=boundary[1],
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T01",
            metric="pii_leakage",
            numerator=pii[0],
            lower_is_better=True,
        ),
        _score(
            model_name=model_name,
            prompt_version="v1",
            case_id="T02",
            metric="pii_leakage",
            numerator=pii[1],
            lower_is_better=True,
        ),
    ]
    return usage, outputs, scores


def _write(tmp_path: Path, usage, outputs, scores) -> tuple[str, str]:  # type: ignore[no-untyped-def]
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
    return report.read_text(encoding="utf-8"), decision.read_text(encoding="utf-8")


def test_pii_or_boundary_disqualifies(tmp_path: Path) -> None:
    m_u, m_o, m_s = _triage_pair(model_name="mistral", queue=(0, 0), pii=(1, 0))
    q_u, q_o, q_s = _triage_pair(model_name="qwen", queue=(1, 1))
    _text, decision = _write(tmp_path, m_u + q_u, m_o + q_o, m_s + q_s)
    assert "selected model: qwen" in decision
    assert "disqualified" in decision

    b_u, b_o, b_s = _triage_pair(model_name="mistral", queue=(1, 1), boundary=(1, 0))
    q2_u, q2_o, q2_s = _triage_pair(model_name="qwen", queue=(0, 0))
    _text, decision = _write(tmp_path, b_u + q2_u, b_o + q2_o, b_s + q2_s)
    assert "selected model: qwen" in decision
    assert "disqualified" in decision


def test_triage_key_order_and_latency_tiebreak(tmp_path: Path) -> None:
    # Equal queue; qwen wins on escalation.
    m_u, m_o, m_s = _triage_pair(
        model_name="mistral", queue=(1, 1), escalation=(1, 0)
    )
    q_u, q_o, q_s = _triage_pair(model_name="qwen", queue=(1, 1), escalation=(1, 1))
    _text, decision = _write(tmp_path, m_u + q_u, m_o + q_o, m_s + q_s)
    assert "selected model: qwen" in decision

    # Equal quality; lower median latency wins.
    m_u, m_o, m_s = _triage_pair(
        model_name="mistral", queue=(1, 1), latency_ms=(400.0, 500.0)
    )
    q_u, q_o, q_s = _triage_pair(
        model_name="qwen", queue=(1, 1), latency_ms=(100.0, 120.0)
    )
    _text, decision = _write(tmp_path, m_u + q_u, m_o + q_o, m_s + q_s)
    assert "selected model: qwen" in decision


def test_extraction_prefers_recall_then_names_failures(tmp_path: Path) -> None:
    usage = [
        _usage(
            model_name="mistral",
            prompt_version="v2",
            case_id="E01",
            latency_ms=100,
            task="extraction",
        ),
        _usage(
            model_name="qwen",
            prompt_version="v2",
            case_id="E01",
            latency_ms=200,
            task="extraction",
        ),
        _usage(
            model_name="qwen",
            prompt_version="v2",
            case_id="E02",
            latency_ms=200,
            task="extraction",
        ),
    ]
    outputs = [
        _output(
            model_name="mistral",
            prompt_version="v2",
            case_id="E01",
            task="extraction",
        ),
        _output(
            model_name="qwen",
            prompt_version="v2",
            case_id="E01",
            task="extraction",
        ),
        _output(
            model_name="qwen",
            prompt_version="v2",
            case_id="E02",
            succeeded=False,
            task="extraction",
        ),
    ]
    scores = [
        _score(
            model_name="mistral",
            prompt_version="v2",
            case_id="E01",
            metric="required_evidence_recall",
            numerator=6,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E01",
            metric="required_evidence_recall",
            numerator=6,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E02",
            metric="required_evidence_recall",
            numerator=0,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="mistral",
            prompt_version="v2",
            case_id="E01",
            metric="citation_correctness",
            numerator=6,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E01",
            metric="citation_correctness",
            numerator=6,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E02",
            metric="citation_correctness",
            numerator=0,
            denominator=6,
            task="extraction",
        ),
        _score(
            model_name="mistral",
            prompt_version="v2",
            case_id="E01",
            metric="unsupported_field_avoidance",
            numerator=1,
            denominator=1,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E01",
            metric="unsupported_field_avoidance",
            numerator=1,
            denominator=1,
            task="extraction",
        ),
        _score(
            model_name="qwen",
            prompt_version="v2",
            case_id="E02",
            metric="unsupported_field_avoidance",
            numerator=0,
            denominator=1,
            task="extraction",
        ),
    ]
    text, decision = _write(tmp_path, usage, outputs, scores)
    assert "selected model: mistral" in decision
    assert "required_evidence_recall (6/6)" in decision
    assert "1 failed" in decision
    assert "scored as zeros" in text
    assert "1 evaluation produced no validated output" in text
