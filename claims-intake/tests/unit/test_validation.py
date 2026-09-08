"""Unit tests for the section 4 rule table.

Written against `docs/api-contract.md` and `docs/requirements-brief.md`.
One parametrized test per rule. Boundaries are inclusive as written except
V-7, which uses a strict `<`.

Run:

    uv run pytest tests/unit/test_validation.py -q
"""

from __future__ import annotations

import pytest

from claims.models import AdmittedNotification, NotificationRequest, RecordedNotification
from claims.policy_client import StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import ValidationOutcome, evaluate_notification, submit_notification


def _request(**overrides: object) -> NotificationRequest:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    payload.update(overrides)
    return NotificationRequest.model_validate(payload)


@pytest.fixture
def repo() -> NotificationRepository:
    return NotificationRepository()


def _assert_passed(outcome: ValidationOutcome) -> None:
    assert outcome.passed is True


def _assert_failed(outcome: ValidationOutcome, rule: str, code: str) -> None:
    assert outcome.passed is False
    assert outcome.rule == rule
    assert outcome.code == code


def _assert_not_recorded(
    request: NotificationRequest,
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
) -> ValidationOutcome:
    result = submit_notification(request, policy_client, repo)
    assert isinstance(result, ValidationOutcome)
    assert result.passed is False
    assert repo.find_matching(request) is None
    return result


def _assert_recorded(
    request: NotificationRequest,
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
) -> RecordedNotification:
    result = submit_notification(request, policy_client, repo)
    assert isinstance(result, RecordedNotification)
    assert result.status == "recorded"
    assert repo.find_matching(request) is not None
    return result


@pytest.mark.parametrize(
    ("overrides", "expect_rule", "expect_code"),
    [
        pytest.param({}, None, None, id="V-1-policy-exists"),
        pytest.param(
            {"policy_number": "MOT-0000"},
            "V-1",
            "POLICY_NOT_FOUND",
            id="V-1-policy-absent",
        ),
        pytest.param(
            {"policy_number": "mot-4471"},
            "V-1",
            "POLICY_NOT_FOUND",
            id="V-1-case-sensitive-EDGE-07",
        ),
        pytest.param(
            {"policy_number": "MOT-0000", "loss_date": "2026-02-11"},
            "V-1",
            "POLICY_NOT_FOUND",
            id="WI-0142-AC-4-not-evaluated-against-inception",
        ),
    ],
)
def test_v1_policy_exists(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    overrides: dict[str, object],
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(**overrides)
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    assert outcome.code != "LOSS_BEFORE_INCEPTION"
    submitted = _assert_not_recorded(request, policy_client, repo)
    _assert_failed(submitted, expect_rule, expect_code)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("duplicate", id="WI-0151-AC-1-AC-2-same-triple"),
        pytest.param("differ_policy_number", id="V-6-not-duplicate-policy-number"),
        pytest.param("differ_loss_date", id="V-6-not-duplicate-loss-date"),
        pytest.param("differ_claim_type", id="V-6-not-duplicate-claim-type"),
        pytest.param("rejected_is_not_recorded", id="WI-0151-AC-3-absence"),
    ],
)
def test_v6_duplicate_notification(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    case: str,
) -> None:
    if case == "rejected_is_not_recorded":
        request = _request(
            policy_number="MOT-4502",
            loss_date="2026-03-19",
            estimated_amount="26000.00",
        )
        first = evaluate_notification(request, policy_client, repo)
        _assert_failed(first, "V-4", "AMOUNT_EXCEEDS_LIMIT")
        assert repo.find_matching(request) is None
        second = evaluate_notification(request, policy_client, repo)
        _assert_failed(second, "V-4", "AMOUNT_EXCEEDS_LIMIT")
        assert second.rule != "V-6"
        assert second.code != "DUPLICATE_NOTIFICATION"
        _assert_not_recorded(request, policy_client, repo)
        return

    original = _request()
    recorded = repo.record(AdmittedNotification.admit(original))

    if case == "duplicate":
        outcome = evaluate_notification(original, policy_client, repo)
        _assert_failed(outcome, "V-6", "DUPLICATE_NOTIFICATION")
        assert outcome.detail["claim_reference"] == recorded.claim_reference
        submitted = _assert_not_recorded(original, policy_client, repo)
        _assert_failed(submitted, "V-6", "DUPLICATE_NOTIFICATION")
        assert submitted.detail["claim_reference"] == recorded.claim_reference
        return

    variants: dict[str, dict[str, object]] = {
        "differ_policy_number": {"policy_number": "MOT-4472"},
        "differ_loss_date": {"loss_date": "2026-04-03"},
        "differ_claim_type": {"claim_type": "theft"},
    }
    request = _request(**variants[case])
    outcome = evaluate_notification(request, policy_client, repo)
    _assert_passed(outcome)
    _assert_recorded(request, policy_client, repo)


@pytest.mark.parametrize(
    ("loss_date", "expect_rule", "expect_code"),
    [
        pytest.param(
            "2026-02-28",
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="WI-0142-AC-1-AC-2-day-before-inception",
        ),
        pytest.param("2026-03-01", None, None, id="WI-0142-AC-3-on-inception"),
        pytest.param("2026-03-02", None, None, id="V-2-day-after-inception"),
    ],
)
def test_v2_loss_date_against_inception(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    loss_date: str,
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(loss_date=loss_date)
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    _assert_not_recorded(request, policy_client, repo)


@pytest.mark.parametrize(
    ("overrides", "expect_rule", "expect_code"),
    [
        pytest.param({}, None, None, id="WI-0158-AC-3-cancellation-date-absent"),
        pytest.param(
            {"policy_number": "MOT-4496", "loss_date": "2026-01-31"},
            None,
            None,
            id="V-7-day-before-cancellation",
        ),
        pytest.param(
            {"policy_number": "MOT-4496", "loss_date": "2026-02-01"},
            "V-7",
            "POLICY_CANCELLED",
            id="WI-0158-AC-2-loss-on-cancellation-date",
        ),
        pytest.param(
            {"policy_number": "MOT-4496", "loss_date": "2026-02-02"},
            "V-7",
            "POLICY_CANCELLED",
            id="WI-0158-AC-1-loss-after-cancellation",
        ),
        pytest.param(
            {"policy_number": "MOT-4496", "loss_date": "2026-09-01"},
            "V-7",
            "POLICY_CANCELLED",
            id="WI-0158-AC-4-cancelled-beats-expiry",
        ),
    ],
)
def test_v7_cancellation(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    overrides: dict[str, object],
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(**overrides)
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    assert outcome.code != "LOSS_AFTER_EXPIRY"
    _assert_not_recorded(request, policy_client, repo)


@pytest.mark.parametrize(
    ("loss_date", "expect_rule", "expect_code"),
    [
        pytest.param("2026-02-27", None, None, id="V-3-day-before-expiry"),
        pytest.param("2026-02-28", None, None, id="V-3-on-expiry"),
        pytest.param(
            "2026-03-01",
            "V-3",
            "LOSS_AFTER_EXPIRY",
            id="V-3-day-after-expiry",
        ),
    ],
)
def test_v3_loss_date_against_expiry(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    loss_date: str,
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(policy_number="MOT-4489", loss_date=loss_date, claim_type="theft")
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    _assert_not_recorded(request, policy_client, repo)


@pytest.mark.parametrize(
    ("estimated_amount", "expect_rule", "expect_code"),
    [
        pytest.param("49999.99", None, None, id="V-4-below-limit"),
        pytest.param("50000.00", None, None, id="V-4-on-limit"),
        pytest.param(
            "50000.01",
            "V-4",
            "AMOUNT_EXCEEDS_LIMIT",
            id="V-4-above-limit",
        ),
    ],
)
def test_v4_amount_against_limit(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    estimated_amount: str,
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(policy_number="MOT-4501", estimated_amount=estimated_amount)
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    _assert_not_recorded(request, policy_client, repo)


@pytest.mark.parametrize(
    ("overrides", "expect_rule", "expect_code"),
    [
        pytest.param(
            {"policy_number": "MOT-4481", "claim_type": "theft"},
            None,
            None,
            id="V-5-type-permitted-named-perils",
        ),
        pytest.param(
            {"policy_number": "MOT-4481", "claim_type": "collision"},
            "V-5",
            "TYPE_NOT_COVERED",
            id="V-5-type-not-permitted-named-perils",
        ),
        pytest.param(
            {"policy_number": "MOT-4486", "claim_type": "liability"},
            None,
            None,
            id="V-5-type-permitted-liability-only",
        ),
        pytest.param(
            {"policy_number": "MOT-4486", "claim_type": "glass"},
            "V-5",
            "TYPE_NOT_COVERED",
            id="V-5-type-not-permitted-liability-only",
        ),
    ],
)
def test_v5_claim_type_permitted(
    policy_client: StubPolicyClient,
    repo: NotificationRepository,
    overrides: dict[str, object],
    expect_rule: str | None,
    expect_code: str | None,
) -> None:
    request = _request(**overrides)
    outcome = evaluate_notification(request, policy_client, repo)
    if expect_rule is None:
        _assert_passed(outcome)
        _assert_recorded(request, policy_client, repo)
        return
    _assert_failed(outcome, expect_rule, expect_code)
    _assert_not_recorded(request, policy_client, repo)
