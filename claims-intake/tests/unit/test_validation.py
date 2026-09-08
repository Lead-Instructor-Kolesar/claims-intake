from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest

from claims.models import ClaimType, NotificationRequest, Policy, RecordedNotification
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    ValidationOutcome,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_notification,
    evaluate_policy_exists,
    submit_notification,
)

INCEPTION = date(2026, 3, 1)
EXPIRY = date(2027, 2, 28)
CANCELLATION = date(2026, 6, 15)
LIMIT = Decimal("50000.00")


def make_notification(**overrides: Any) -> NotificationRequest:
    body: dict[str, Any] = {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }
    body.update(overrides)
    return NotificationRequest(**body)


def make_policy(**overrides: Any) -> Policy:
    body: dict[str, Any] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": INCEPTION,
        "expiry_date": EXPIRY,
        "cancellation_date": None,
        "limit": LIMIT,
        "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
    }
    body.update(overrides)
    return Policy(**body)


def assert_passed(outcome: ValidationOutcome) -> None:
    assert outcome.passed is True
    assert outcome.rule is None
    assert outcome.code is None


def assert_failed(
    outcome: ValidationOutcome,
    *,
    rule: str,
    code: str,
    **detail: Any,
) -> None:
    assert outcome.passed is False
    assert outcome.rule == rule
    assert outcome.code == code
    for key, value in detail.items():
        assert outcome.detail[key] == value


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


def test_evaluate_notification_takes_only_notification_and_policy() -> None:
    parameters = inspect.signature(evaluate_notification).parameters
    assert list(parameters) == ["notification", "policy"]


def test_evaluate_notification_performs_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    record = Mock()
    get_policy = Mock()
    monkeypatch.setattr(NotificationRepository, "record", record)
    monkeypatch.setattr(StubPolicyClient, "get_policy", get_policy)

    evaluate_notification(make_notification(), make_policy())

    record.assert_not_called()
    get_policy.assert_not_called()


@pytest.mark.parametrize(
    "policy_number, expected_passed",
    [
        pytest.param("MOT-4471", True, id="policy_exists"),
        pytest.param("MOT-9999", False, id="policy_missing"),
        pytest.param("mot-4471", False, id="policy_number_case_mismatch"),
    ],
)
def test_v1_policy_exists(
    policy_client: StubPolicyClient,
    policy_number: str,
    expected_passed: bool,
) -> None:
    notification = make_notification(policy_number=policy_number)
    outcome = evaluate_policy_exists(notification, policy_client)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=policy_number,
        )


@pytest.mark.parametrize(
    "loss_date, expected_passed",
    [
        pytest.param(date(2026, 2, 28), False, id="day_before_inception"),
        pytest.param(date(2026, 3, 1), True, id="on_inception_date"),
        pytest.param(date(2026, 3, 2), True, id="day_after_inception"),
    ],
)
def test_v2_loss_after_inception_boundary(loss_date: date, expected_passed: bool) -> None:
    """WI-0142 AC-3: a loss on the inception date is covered."""
    policy = make_policy(effective_date=INCEPTION)
    notification = make_notification(loss_date=loss_date)
    outcome = evaluate_loss_after_inception(notification, policy)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-2",
            code="LOSS_BEFORE_INCEPTION",
            loss_date=loss_date,
            effective_date=INCEPTION,
        )


@pytest.mark.parametrize(
    "loss_date, expected_passed",
    [
        pytest.param(date(2027, 2, 27), True, id="day_before_expiry"),
        pytest.param(date(2027, 2, 28), True, id="on_expiry_date"),
        pytest.param(date(2027, 3, 1), False, id="day_after_expiry"),
    ],
)
def test_v3_loss_before_expiry_boundary(loss_date: date, expected_passed: bool) -> None:
    policy = make_policy(expiry_date=EXPIRY)
    notification = make_notification(loss_date=loss_date)
    outcome = evaluate_loss_before_expiry(notification, policy)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-3",
            code="LOSS_AFTER_EXPIRY",
            loss_date=loss_date,
            expiry_date=EXPIRY,
        )


@pytest.mark.parametrize(
    "estimated_amount, expected_passed",
    [
        pytest.param(Decimal("49999.99"), True, id="amount_below_limit"),
        pytest.param(Decimal("50000.00"), True, id="amount_equal_to_limit"),
        pytest.param(Decimal("50000.01"), False, id="amount_above_limit"),
    ],
)
def test_v4_amount_within_limit_boundary(
    estimated_amount: Decimal,
    expected_passed: bool,
) -> None:
    policy = make_policy(limit=LIMIT)
    notification = make_notification(estimated_amount=estimated_amount)
    outcome = evaluate_amount_within_limit(notification, policy)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-4",
            code="AMOUNT_EXCEEDS_LIMIT",
            estimated_amount=estimated_amount,
            limit=LIMIT,
        )


@pytest.mark.parametrize(
    "claim_type, permitted, expected_passed",
    [
        pytest.param(
            "collision",
            ("collision", "theft", "glass", "liability", "weather"),
            True,
            id="claim_type_permitted",
        ),
        pytest.param(
            "collision",
            ("theft", "glass", "weather", "liability"),
            False,
            id="collision_not_on_named_perils",
        ),
    ],
)
def test_v5_claim_type_covered(
    claim_type: ClaimType,
    permitted: tuple[ClaimType, ...],
    expected_passed: bool,
) -> None:
    policy = make_policy(permitted_claim_types=permitted)
    notification = make_notification(claim_type=claim_type)
    outcome = evaluate_claim_type_covered(notification, policy)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-5",
            code="TYPE_NOT_COVERED",
            claim_type=claim_type,
        )


@pytest.mark.parametrize(
    "already_recorded, expected_duplicate",
    [
        pytest.param(False, False, id="no_prior_record"),
        pytest.param(True, True, id="matching_recorded_is_duplicate"),
    ],
)
def test_v6_duplicate_of_recorded_notification(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    already_recorded: bool,
    expected_duplicate: bool,
) -> None:
    notification = make_notification()
    if already_recorded:
        recorded = repository.record(notification)
    else:
        recorded = None

    result = submit_notification(notification, policy_client, repository)

    if expected_duplicate:
        assert recorded is not None
        assert isinstance(result, ValidationOutcome)
        assert_failed(
            result,
            rule="V-6",
            code="DUPLICATE_NOTIFICATION",
            claim_reference=recorded.claim_reference,
        )
    else:
        assert isinstance(result, RecordedNotification)
        assert result.status == "recorded"


def test_v6_rejected_notification_is_not_a_duplicate(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """WI-0151 AC-3: a matching previous submission that was rejected is not a duplicate."""
    rejected = make_notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 19),
        claim_type="collision",
        estimated_amount=Decimal("26000.00"),
        description="Above the limit on a policy whose product permits collision.",
    )
    first = submit_notification(rejected, policy_client, repository)
    assert isinstance(first, ValidationOutcome)
    assert first.code == "AMOUNT_EXCEEDS_LIMIT"

    retry = make_notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 19),
        claim_type="collision",
        estimated_amount=Decimal("1250.00"),
        description="Low speed impact with a bollard.",
    )
    second = submit_notification(retry, policy_client, repository)
    assert isinstance(second, RecordedNotification)
    assert second.status == "recorded"


@pytest.mark.parametrize(
    "loss_date, cancellation_date, expected_passed",
    [
        pytest.param(date(2026, 6, 14), CANCELLATION, True, id="day_before_cancellation"),
        pytest.param(date(2026, 6, 15), CANCELLATION, False, id="on_cancellation_date"),
        pytest.param(date(2026, 6, 16), CANCELLATION, False, id="day_after_cancellation"),
        pytest.param(date(2026, 6, 15), None, True, id="cancellation_date_absent"),
    ],
)
def test_v7_cancellation_boundary(
    loss_date: date,
    cancellation_date: date | None,
    expected_passed: bool,
) -> None:
    """V-7 uses <: a loss on the cancellation date is not covered (WI-0158 AC-2).

    WI-0158 AC-3: where cancellation_date is null this rule does not apply.
    """
    policy = make_policy(cancellation_date=cancellation_date)
    notification = make_notification(loss_date=loss_date)
    outcome = evaluate_notification(notification, policy)
    if expected_passed:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-7",
            code="POLICY_CANCELLED",
            loss_date=loss_date,
            cancellation_date=cancellation_date,
        )


@pytest.mark.parametrize(
    "notification, policy, expected_rule, expected_code",
    [
        pytest.param(
            make_notification(
                policy_number="MOT-4500",
                loss_date=date(2026, 1, 8),
                claim_type="collision",
                estimated_amount=Decimal("6000.00"),
                description="Loss after cancellation and after the original expiry date.",
            ),
            make_policy(
                policy_number="MOT-4500",
                effective_date=date(2025, 1, 1),
                expiry_date=date(2025, 12, 31),
                cancellation_date=date(2025, 10, 1),
                limit=Decimal("45000.00"),
            ),
            "V-7",
            "POLICY_CANCELLED",
            id="cancelled_and_after_expiry_reports_cancelled",
        ),
        pytest.param(
            make_notification(
                policy_number="MOT-4493",
                loss_date=date(2026, 3, 2),
                claim_type="collision",
                estimated_amount=Decimal("72000.00"),
                description="Loss before inception and above the limit.",
            ),
            make_policy(
                policy_number="MOT-4493",
                effective_date=date(2026, 4, 15),
                expiry_date=date(2027, 4, 14),
                limit=Decimal("50000.00"),
            ),
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="before_inception_and_over_limit_reports_inception",
        ),
    ],
)
def test_evaluate_notification_stops_at_the_first_failure(
    notification: NotificationRequest,
    policy: Policy,
    expected_rule: str,
    expected_code: str,
) -> None:
    outcome = evaluate_notification(notification, policy)
    assert outcome.passed is False
    assert outcome.rule == expected_rule
    assert outcome.code == expected_code


def test_submit_notification_policy_not_found_is_v1(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    notification = make_notification(policy_number="MOT-9999")
    result = submit_notification(notification, policy_client, repository)
    assert isinstance(result, ValidationOutcome)
    assert_failed(
        result,
        rule="V-1",
        code="POLICY_NOT_FOUND",
        policy_number="MOT-9999",
    )
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="timeout"),
        pytest.param("unreachable", id="unreachable"),
        pytest.param("unparsable", id="unparsable"),
    ],
)
def test_submit_notification_propagates_policy_lookup_failed(
    reason: LookupFailureReason,
    repository: NotificationRepository,
) -> None:
    client = StubPolicyClient(fail_with=reason)
    notification = make_notification()
    with pytest.raises(PolicyLookupFailed) as exc_info:
        submit_notification(notification, client, repository)
    assert exc_info.value.reason == reason
    assert exc_info.value.policy_number == notification.policy_number
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )


def test_submit_notification_does_not_record_on_rule_failure(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = Mock(wraps=repository.record)
    monkeypatch.setattr(repository, "record", record)
    notification = make_notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 19),
        estimated_amount=Decimal("26000.00"),
        description="Above the limit on a policy whose product permits collision.",
    )
    result = submit_notification(notification, policy_client, repository)
    assert isinstance(result, ValidationOutcome)
    assert result.passed is False
    record.assert_not_called()
