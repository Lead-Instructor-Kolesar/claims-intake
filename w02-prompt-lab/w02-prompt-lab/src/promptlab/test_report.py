from decimal import Decimal

from promptlab.records import OutputRecord, ScoreRecord, UsageRecord
from promptlab.report import write_reports


def test_report_is_generated_from_records(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    usage = [
        UsageRecord(
            run_id="demo",
            task="triage",
            case_id="T01",
            model_name="mistral",
            model_id="mistral:7b",
            prompt_version="triage-mistral-v1",
            attempt=1,
            kind="primary",
            status="success",
            prompt_tokens=100,
            completion_tokens=25,
            latency_ms=125.0,
            cost_usd=Decimal("0"),
        )
    ]
    outputs = [
        OutputRecord(
            run_id="demo",
            task="triage",
            case_id="T01",
            model_name="mistral",
            model_id="mistral:7b",
            prompt_version="triage-mistral-v1",
            succeeded=True,
            repairs=0,
            output={"queue": "card_dispute"},
        )
    ]
    scores = [
        ScoreRecord(
            run_id="demo",
            task="triage",
            case_id="T01",
            model_name="mistral",
            prompt_version="triage-mistral-v1",
            scorer_version="2.0.0",
            metric="queue_accuracy",
            numerator=1,
            denominator=1,
        )
    ]
    report = root / "comparison.md"
    decision = root / "model-decision.md"
    write_reports(
        run_id="demo",
        models=["mistral"],
        usage=usage,
        outputs=outputs,
        scores=scores,
        report_path=report,
        decision_path=decision,
    )
    assert "1/1" in report.read_text(encoding="utf-8")
    assert "triage-mistral-v1" in report.read_text(encoding="utf-8")
    assert "mistral" in decision.read_text(encoding="utf-8")

