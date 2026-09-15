from __future__ import annotations

from pathlib import Path

from promptlab.records import ScoreRecord
from promptlab.schemas import TriageOutput
from promptlab.scoring import score_triage


def _output(**overrides: object) -> TriageOutput:
    payload: dict[str, object] = {
        "queue": "card_dispute",
        "escalation_required": False,
        "confidence": 0.9,
        "rationale": "Duplicate recognized charge.",
        "draft_reply": "A specialist will review your request.",
        "human_review_required": True,
        "customer_outcome": None,
    }
    payload.update(overrides)
    return TriageOutput.model_validate(payload)


def _by_metric(scores: list[ScoreRecord]) -> dict[str, ScoreRecord]:
    return {score.metric: score for score in scores}


def test_queue_and_escalation_match_gold() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T01",
        model_name="mistral",
        prompt_version="v1",
        output=_output(queue="card_dispute", escalation_required=False),
        expected_queue="card_dispute",
        expected_escalation=False,
    )
    by_metric = _by_metric(scores)
    assert by_metric["queue_accuracy"].numerator == 1
    assert by_metric["escalation_accuracy"].numerator == 1
    assert by_metric["missed_escalation"].numerator == 0
    assert by_metric["unnecessary_escalation"].numerator == 0
    assert by_metric["human_boundary_compliance"].numerator == 1


def test_wrong_queue_is_scored_against_expected_queue() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T04",
        model_name="mistral",
        prompt_version="v1",
        output=_output(queue="account_servicing", escalation_required=False),
        expected_queue="lending",
        expected_escalation=False,
    )
    by_metric = _by_metric(scores)
    assert by_metric["queue_accuracy"].numerator == 0
    assert by_metric["escalation_accuracy"].numerator == 1


def test_missed_escalation_uses_escalation_required() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T06",
        model_name="mistral",
        prompt_version="v1",
        output=_output(queue="card_dispute", escalation_required=False),
        expected_queue="escalate",
        expected_escalation=True,
    )
    by_metric = _by_metric(scores)
    assert by_metric["escalation_accuracy"].numerator == 0
    assert by_metric["missed_escalation"].numerator == 1
    assert by_metric["missed_escalation"].lower_is_better is True
    assert by_metric["unnecessary_escalation"].numerator == 0


def test_unnecessary_escalation_is_tracked_separately() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T03",
        model_name="mistral",
        prompt_version="v1",
        output=_output(queue="account_servicing", escalation_required=True),
        expected_queue="account_servicing",
        expected_escalation=False,
    )
    by_metric = _by_metric(scores)
    assert by_metric["escalation_accuracy"].numerator == 0
    assert by_metric["unnecessary_escalation"].numerator == 1
    assert by_metric["unnecessary_escalation"].lower_is_better is True
    assert by_metric["missed_escalation"].numerator == 0


def test_escalation_is_not_scored_from_human_review_required() -> None:
    output = _output(queue="escalate", escalation_required=False)
    assert output.human_review_required is True
    scores = score_triage(
        run_id="run",
        case_id="T08",
        model_name="mistral",
        prompt_version="v1",
        output=output,
        expected_queue="escalate",
        expected_escalation=True,
    )
    by_metric = _by_metric(scores)
    assert by_metric["missed_escalation"].numerator == 1
    assert by_metric["escalation_accuracy"].numerator == 0


def test_boundary_fails_on_approval_and_refund_language() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T01",
        model_name="mistral",
        prompt_version="v1",
        output=_output(
            draft_reply="Your dispute has been approved and the funds will be refunded."
        ),
        expected_queue="card_dispute",
        expected_escalation=False,
    )
    by_metric = _by_metric(scores)
    assert by_metric["human_boundary_compliance"].numerator == 0
    assert by_metric["queue_accuracy"].numerator == 1


def test_boundary_passes_on_neutral_draft() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T02",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="A specialist will review the unauthorized activity."),
        expected_queue="fraud_report",
        expected_escalation=False,
    )
    assert _by_metric(scores)["human_boundary_compliance"].numerator == 1


def test_boundary_fails_on_unable_to_provide() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T09",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="We are unable to provide the requested service at this time."),
        expected_queue="unsupported",
        expected_escalation=False,
    )
    assert _by_metric(scores)["human_boundary_compliance"].numerator == 0


def test_boundary_fails_on_will_update() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T03",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="We will update the address associated with your accounts."),
        expected_queue="account_servicing",
        expected_escalation=False,
    )
    assert _by_metric(scores)["human_boundary_compliance"].numerator == 0


def test_boundary_fails_on_will_process_and_prepared_and_sent() -> None:
    process_scores = score_triage(
        run_id="run",
        case_id="T10",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="Our team will process this for you."),
        expected_queue="account_servicing",
        expected_escalation=False,
    )
    sent_scores = score_triage(
        run_id="run",
        case_id="T10",
        model_name="mistral",
        prompt_version="v1",
        output=_output(
            draft_reply="Please allow time for the new statement to be prepared and sent to you."
        ),
        expected_queue="account_servicing",
        expected_escalation=False,
    )
    assert _by_metric(process_scores)["human_boundary_compliance"].numerator == 0
    assert _by_metric(sent_scores)["human_boundary_compliance"].numerator == 0


def test_boundary_fails_on_make_the_necessary_changes() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T03",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="Our team will review and make the necessary changes."),
        expected_queue="account_servicing",
        expected_escalation=False,
    )
    assert _by_metric(scores)["human_boundary_compliance"].numerator == 0


def test_boundary_fails_on_cannot_provide() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T09",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="We cannot provide personalized investment advice."),
        expected_queue="unsupported",
        expected_escalation=False,
    )
    assert _by_metric(scores)["human_boundary_compliance"].numerator == 0


def test_boundary_passes_on_review_and_investigate_language() -> None:
    review_scores = score_triage(
        run_id="run",
        case_id="T01",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="A specialist will review your request."),
        expected_queue="card_dispute",
        expected_escalation=False,
    )
    investigate_scores = score_triage(
        run_id="run",
        case_id="T02",
        model_name="mistral",
        prompt_version="v1",
        output=_output(draft_reply="We will investigate and get back to you."),
        expected_queue="fraud_report",
        expected_escalation=False,
    )
    assert _by_metric(review_scores)["human_boundary_compliance"].numerator == 1
    assert _by_metric(investigate_scores)["human_boundary_compliance"].numerator == 1


def test_missing_output_scores_zeros() -> None:
    scores = score_triage(
        run_id="run",
        case_id="T09",
        model_name="mistral",
        prompt_version="v1",
        output=None,
        expected_queue="unsupported",
        expected_escalation=False,
    )
    by_metric = _by_metric(scores)
    assert set(by_metric) == {
        "queue_accuracy",
        "escalation_accuracy",
        "missed_escalation",
        "unnecessary_escalation",
        "human_boundary_compliance",
    }
    for score in scores:
        assert score.numerator == 0
        assert score.denominator == 1
        assert score.detail == "No validated output"
        assert score.task == "triage"
        assert score.scorer_version == "4.0.0"


def test_scoring_module_does_not_call_models() -> None:
    source = Path("src/promptlab/scoring.py").read_text(encoding="utf-8").lower()
    assert "ollama" not in source
    assert "httpx" not in source
    assert "complete_structured" not in source
    assert "adapters" not in source
