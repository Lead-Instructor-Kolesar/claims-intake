"""Pin V-1..V-7 from contract section 4.2 and the work-item ACs.

Written from docs/api-contract.md and docs/requirements-brief.md, not from
service.py. Each rule has one parametrized test with named ids. Extra tests
cover evaluation order, the policy-master boundary, and recording.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import (
    ClaimType,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleIdentifier,
)
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import evaluate_notification, evaluate_policy_exists, submit_notification

STANDARD_TYPES: tuple[ClaimType, ...] = (
    "collision",
    "theft",
    "glass",
    "liability",
    "weather",
)


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recorded_on=date(2026, 8, 25))


def make_notification(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: Decimal = Decimal("4200.00"),
) -> NotificationRequest:
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
    )


def make_policy(
    *,
    policy_number: str = "MOT-4471",
    product: str = "personal_auto_standard",
    effective_date: date = date(2026, 3, 1),
    expiry_date: date = date(2027, 2, 28),
    cancellation_date: date | None = None,
    limit: Decimal = Decimal("50000.00"),
    permitted_claim_types: tuple[ClaimType, ...] = STANDARD_TYPES,
) -> Policy:
    return Policy(
        policy_number=policy_number,
        product=product,
        effective_date=effective_date,
        expiry_date=expiry_date,
        cancellation_date=cancellation_date,
        limit=limit,
        permitted_claim_types=permitted_claim_types,
    )


@pytest.mark.parametrize(
    ("policy_number", "should_pass"),
    [
        pytest.param("MOT-4471", True, id="V-1-held-identifier-passes"),
        pytest.param("mot-4471", False, id="V-1-case-differs-POLICY_NOT_FOUND"),
        pytest.param("MOT-0000", False, id="V-1-unknown-identifier-POLICY_NOT_FOUND"),
    ],
)
def test_v1_policy_exists_is_exact_case_sensitive_match(
    policy_client: StubPolicyClient, policy_number: str, should_pass: bool
) -> None:
    notification = make_notification(policy_number=policy_number)
    outcome = evaluate_policy_exists(notification, policy_client)
    assert outcome.passed is should_pass
    if not should_pass:
        assert outcome.rule == "V-1"
        assert outcome.code == "POLICY_NOT_FOUND"
        assert outcome.detail["policy_number"] == policy_number


@pytest.mark.parametrize(
    ("loss_date", "expected"),
    [
        pytest.param(
            date(2026, 2, 28),
            RuleFailure(rule="V-2", code="LOSS_BEFORE_INCEPTION"),
            id="V-2-day-before-inception-fails",
        ),
        pytest.param(
            date(2026, 3, 1),
            None,
            id="V-2-WI-0142-AC-3-on-inception-passes",
        ),
        pytest.param(
            date(2026, 3, 2),
            None,
            id="V-2-day-after-inception-passes",
        ),
    ],
)
def test_v2_loss_date_against_effective_date(
    loss_date: date, expected: RuleFailure | None
) -> None:
    # MOT-4471 effective_date 2026-03-01. Condition: loss_date >= effective_date.
    notification = make_notification(loss_date=loss_date)
    policy = make_policy()
    assert evaluate_notification(notification, policy) == expected


@pytest.mark.parametrize(
    ("loss_date", "expected"),
    [
        pytest.param(date(2026, 2, 27), None, id="V-3-day-before-expiry-passes"),
        pytest.param(date(2026, 2, 28), None, id="V-3-on-expiry-passes"),
        pytest.param(
            date(2026, 3, 1),
            RuleFailure(rule="V-3", code="LOSS_AFTER_EXPIRY"),
            id="V-3-day-after-expiry-fails",
        ),
    ],
)
def test_v3_loss_date_against_expiry_date(
    loss_date: date, expected: RuleFailure | None
) -> None:
    # MOT-4489 expiry_date 2026-02-28. Condition: loss_date <= expiry_date.
    notification = make_notification(
        policy_number="MOT-4489",
        loss_date=loss_date,
        claim_type="theft",
        estimated_amount=Decimal("9000.00"),
    )
    policy = make_policy(
        policy_number="MOT-4489",
        effective_date=date(2025, 3, 1),
        expiry_date=date(2026, 2, 28),
    )
    assert evaluate_notification(notification, policy) == expected


@pytest.mark.parametrize(
    ("estimated_amount", "expected"),
    [
        pytest.param(Decimal("49999.99"), None, id="V-4-under-limit-passes"),
        pytest.param(Decimal("50000.00"), None, id="V-4-equal-to-limit-passes"),
        pytest.param(
            Decimal("50000.01"),
            RuleFailure(rule="V-4", code="AMOUNT_EXCEEDS_LIMIT"),
            id="V-4-over-limit-fails",
        ),
    ],
)
def test_v4_estimated_amount_against_limit(
    estimated_amount: Decimal, expected: RuleFailure | None
) -> None:
    notification = make_notification(estimated_amount=estimated_amount)
    policy = make_policy(limit=Decimal("50000.00"))
    assert evaluate_notification(notification, policy) == expected


@pytest.mark.parametrize(
    ("claim_type", "permitted", "expected"),
    [
        pytest.param(
            "collision",
            STANDARD_TYPES,
            None,
            id="V-5-permitted-vocabulary-value-passes",
        ),
        pytest.param(
            "liability",
            ("liability",),
            None,
            id="V-5-only-member-of-permitted-set-passes",
        ),
        pytest.param(
            "collision",
            ("theft", "glass", "weather", "liability"),
            RuleFailure(rule="V-5", code="TYPE_NOT_COVERED"),
            id="V-5-collision-not-on-named-perils-fails",
        ),
    ],
)
def test_v5_claim_type_against_permitted_claim_types(
    claim_type: ClaimType,
    permitted: tuple[ClaimType, ...],
    expected: RuleFailure | None,
) -> None:
    notification = make_notification(claim_type=claim_type)
    policy = make_policy(permitted_claim_types=permitted)
    assert evaluate_notification(notification, policy) == expected


@pytest.mark.parametrize(
    ("second_policy", "second_date", "second_type", "should_pass"),
    [
        pytest.param(
            "MOT-4471",
            date(2026, 4, 2),
            "collision",
            False,
            id="V-6-WI-0151-AC-1-all-three-match-fails",
        ),
        pytest.param(
            "MOT-4471",
            date(2026, 4, 2),
            "theft",
            True,
            id="V-6-same-policy-date-different-type-passes",
        ),
        pytest.param(
            "MOT-4471",
            date(2026, 4, 3),
            "collision",
            True,
            id="V-6-same-policy-type-different-date-passes",
        ),
        pytest.param(
            "MOT-4472",
            date(2026, 4, 2),
            "collision",
            True,
            id="V-6-same-date-type-different-policy-passes",
        ),
    ],
)
def test_v6_duplicate_is_the_three_field_composite(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    second_policy: str,
    second_date: date,
    second_type: ClaimType,
    should_pass: bool,
) -> None:
    first = make_notification()
    first_outcome = submit_notification(first, policy_client, repository)
    assert first_outcome.passed is True
    second = make_notification(
        policy_number=second_policy,
        loss_date=second_date,
        claim_type=second_type,
    )
    second_outcome = submit_notification(second, policy_client, repository)
    assert second_outcome.passed is should_pass
    if not should_pass:
        assert second_outcome.failure == RuleFailure(
            rule="V-6", code="DUPLICATE_NOTIFICATION"
        )
        assert second_outcome.detail["claim_reference"] == first_outcome.claim_reference
        assert (
            repository.find_matching(
                second.policy_number, second.loss_date, second.claim_type
            )
            is not None
        )
        assert repository.allocate_claim_reference() == "CLM-2026-000002"


@pytest.mark.parametrize(
    ("cancellation_date", "loss_date", "expected"),
    [
        pytest.param(
            None,
            date(2026, 4, 2),
            None,
            id="V-7-WI-0158-AC-3-null-cancellation-passes",
        ),
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 14),
            None,
            id="V-7-day-before-cancellation-passes",
        ),
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 15),
            RuleFailure(rule="V-7", code="POLICY_CANCELLED"),
            id="V-7-WI-0158-AC-2-on-cancellation-date-fails",
        ),
        pytest.param(
            date(2026, 1, 15),
            date(2026, 1, 16),
            RuleFailure(rule="V-7", code="POLICY_CANCELLED"),
            id="V-7-day-after-cancellation-fails",
        ),
    ],
)
def test_v7_loss_date_against_cancellation_date(
    cancellation_date: date | None,
    loss_date: date,
    expected: RuleFailure | None,
) -> None:
    # Condition: cancellation_date is null OR loss_date < cancellation_date.
    notification = make_notification(loss_date=loss_date)
    policy = make_policy(
        effective_date=date(2025, 6, 1),
        expiry_date=date(2026, 5, 31),
        cancellation_date=cancellation_date,
    )
    assert evaluate_notification(notification, policy) == expected


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type", "amount", "rule", "code"),
    [
        pytest.param(
            "MOT-4493",
            date(2026, 3, 2),
            "collision",
            Decimal("72000.00"),
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="order-V-2-before-V-4-when-both-would-fail",
        ),
        pytest.param(
            "MOT-4500",
            date(2026, 1, 8),
            "collision",
            Decimal("6000.00"),
            "V-7",
            "POLICY_CANCELLED",
            id="order-WI-0158-AC-4-V-7-before-V-3",
        ),
        pytest.param(
            "MOT-4481",
            date(2026, 3, 27),
            "collision",
            Decimal("4800.00"),
            "V-5",
            "TYPE_NOT_COVERED",
            id="order-V-5-when-cover-period-passes",
        ),
    ],
)
def test_evaluate_notification_stops_at_the_first_section_4_1_failure(
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
    amount: Decimal,
    rule: RuleIdentifier,
    code: ErrorCode,
) -> None:
    notification = make_notification(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=amount,
    )
    # Policies match data/policies.json so order cases are the real EDGE payloads.
    policies = {
        "MOT-4493": make_policy(
            policy_number="MOT-4493",
            effective_date=date(2026, 4, 15),
            expiry_date=date(2027, 4, 14),
            limit=Decimal("50000.00"),
        ),
        "MOT-4500": make_policy(
            policy_number="MOT-4500",
            effective_date=date(2025, 1, 1),
            expiry_date=date(2025, 12, 31),
            cancellation_date=date(2025, 10, 1),
            limit=Decimal("45000.00"),
        ),
        "MOT-4481": make_policy(
            policy_number="MOT-4481",
            product="personal_auto_named_perils",
            effective_date=date(2026, 2, 15),
            expiry_date=date(2027, 2, 14),
            limit=Decimal("30000.00"),
            permitted_claim_types=("theft", "glass", "weather", "liability"),
        ),
    }
    failure = evaluate_notification(notification, policies[policy_number])
    assert failure == RuleFailure(rule=rule, code=code)


@pytest.mark.parametrize(
    "policy_number",
    [pytest.param("MOT-4471", id="submit-records-when-every-rule-passes")],
)
def test_submit_notification_records_only_when_every_rule_passes(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    policy_number: str,
) -> None:
    notification = make_notification(policy_number=policy_number)
    outcome = submit_notification(notification, policy_client, repository)
    assert outcome.passed is True
    assert outcome.failure is None
    assert outcome.claim_reference is not None
    found = repository.find_matching(
        notification.policy_number, notification.loss_date, notification.claim_type
    )
    assert found is not None
    assert found.claim_reference == outcome.claim_reference


@pytest.mark.parametrize(
    "policy_number",
    [pytest.param("mot-4471", id="submit-WI-0142-AC-4-unknown-is-V-1-not-V-2")],
)
def test_submit_notification_policy_not_found_is_v1_and_records_nothing(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    policy_number: str,
) -> None:
    notification = make_notification(
        policy_number=policy_number, loss_date=date(2020, 1, 1)
    )
    outcome = submit_notification(notification, policy_client, repository)
    assert outcome.passed is False
    assert outcome.failure == RuleFailure(rule="V-1", code="POLICY_NOT_FOUND")
    assert outcome.claim_reference is None
    assert (
        repository.find_matching(
            notification.policy_number, notification.loss_date, notification.claim_type
        )
        is None
    )


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="lookup-failed-timeout-propagates"),
        pytest.param("unreachable", id="lookup-failed-unreachable-propagates"),
        pytest.param("unparsable", id="lookup-failed-unparsable-propagates"),
    ],
)
def test_submit_notification_propagates_policy_lookup_failed(
    repository: NotificationRepository, reason: LookupFailureReason
) -> None:
    notification = make_notification()
    client = StubPolicyClient(fail_with=reason)
    with pytest.raises(PolicyLookupFailed) as caught:
        submit_notification(notification, client, repository)
    assert caught.value.reason == reason
    assert caught.value.policy_number == notification.policy_number
    assert (
        repository.find_matching(
            notification.policy_number, notification.loss_date, notification.claim_type
        )
        is None
    )


@pytest.mark.parametrize(
    "policy_number",
    [pytest.param("MOT-4502", id="submit-WI-0151-AC-3-rejected-then-valid-records")],
)
def test_submit_rejected_notification_is_not_a_duplicate_on_resubmit(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    policy_number: str,
) -> None:
    over_limit = make_notification(
        policy_number=policy_number,
        loss_date=date(2026, 3, 19),
        estimated_amount=Decimal("26000.00"),
    )
    refused = submit_notification(over_limit, policy_client, repository)
    assert refused.passed is False
    assert refused.failure == RuleFailure(rule="V-4", code="AMOUNT_EXCEEDS_LIMIT")
    assert (
        repository.find_matching(
            over_limit.policy_number, over_limit.loss_date, over_limit.claim_type
        )
        is None
    )
    within_limit = make_notification(
        policy_number=policy_number,
        loss_date=date(2026, 3, 19),
        estimated_amount=Decimal("1000.00"),
    )
    accepted = submit_notification(within_limit, policy_client, repository)
    assert accepted.passed is True
    assert accepted.claim_reference is not None
