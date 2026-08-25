"""Unit tests for the rule engine.

Each rule is tested on its own against a typed `Policy`, with the boundary cases
the contract states explicitly. `evaluate_notification` is tested for the staged
order in section 4.1, because which of several violated rules the caller is told
about is a caller-visible behaviour.

No test here builds a raw payload dict for the rules: the rules take
`NotificationRequest` and `Policy`, and nothing else.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import (
    CLAIM_TYPE_VOCABULARY,
    ClaimRecord,
    ClaimType,
    NotificationRequest,
    Policy,
    RuleFailure,
)
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    ValidationOutcome,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_not_duplicate,
    evaluate_notification,
    evaluate_policy_exists,
    evaluate_policy_not_cancelled,
    submit_notification,
)
from tests.payloads import payload


def notification_request(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: Decimal = Decimal("4200.00"),
    description: str | None = "Rear ended at a junction.",
) -> NotificationRequest:
    """A well-formed request. Each call returns a new instance."""
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
        description=description,
    )


def policy(
    *,
    policy_number: str = "MOT-4471",
    product: str = "personal_auto_standard",
    effective_date: date = date(2026, 1, 1),
    expiry_date: date = date(2026, 12, 31),
    cancellation_date: date | None = None,
    limit: Decimal = Decimal("50000.00"),
    permitted_claim_types: tuple[ClaimType, ...] = CLAIM_TYPE_VOCABULARY,
) -> Policy:
    """A policy in force for the whole of 2026. Each call returns a new instance."""
    return Policy(
        policy_number=policy_number,
        product=product,
        effective_date=effective_date,
        expiry_date=expiry_date,
        cancellation_date=cancellation_date,
        limit=limit,
        permitted_claim_types=permitted_claim_types,
    )


def request_from(payload: dict[str, object]) -> NotificationRequest:
    """Parse a payload file entry through the boundary, as the service requires."""
    return NotificationRequest.model_validate(payload)


def test_v1_passes_where_the_master_holds_the_policy(
    policy_client: StubPolicyClient,
) -> None:
    outcome = evaluate_policy_exists(notification_request(), policy_client)
    assert outcome.passed


def test_v1_refuses_policy_the_master_does_not_hold(
    policy_client: StubPolicyClient,
) -> None:
    outcome = evaluate_policy_exists(
        notification_request(policy_number="MOT-9999"), policy_client
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-1",
        code="POLICY_NOT_FOUND",
        policy_number="MOT-9999",
    )


def test_v1_refuses_policy_number_differing_only_in_case() -> None:
    """Determination D-1: the value is looked up unnormalised."""
    outcome = evaluate_policy_exists(
        notification_request(policy_number="mot-4471"), StubPolicyClient()
    )
    assert outcome.code == "POLICY_NOT_FOUND"


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="master_timed_out"),
        pytest.param("unreachable", id="master_unreachable"),
        pytest.param("unparsable", id="master_answer_unparsable"),
    ],
)
def test_v1_does_not_absorb_a_lookup_failure(reason: LookupFailureReason) -> None:
    """A dependency failure is not the caller's fault, so it must not become a refusal."""
    with pytest.raises(PolicyLookupFailed):
        evaluate_policy_exists(notification_request(), StubPolicyClient(fail_with=reason))


@pytest.mark.parametrize(
    ("loss_date", "expected_pass"),
    [
        pytest.param(date(2026, 3, 14), False, id="day_before_inception_refused"),
        pytest.param(date(2026, 3, 15), True, id="on_inception_covered"),
        pytest.param(date(2026, 3, 16), True, id="day_after_inception_covered"),
    ],
)
def test_v2_treats_inception_as_inclusive(loss_date: date, expected_pass: bool) -> None:
    """WI-0142 AC-3: cover attaches on the day."""
    outcome = evaluate_loss_after_inception(
        notification_request(loss_date=loss_date),
        policy(effective_date=date(2026, 3, 15)),
    )
    assert outcome.passed is expected_pass


def test_v2_refusal_carries_the_two_dates_it_compared() -> None:
    outcome = evaluate_loss_after_inception(
        notification_request(loss_date=date(2026, 3, 2)),
        policy(effective_date=date(2026, 4, 15)),
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-2",
        code="LOSS_BEFORE_INCEPTION",
        policy_number="MOT-4471",
        loss_date=date(2026, 3, 2),
        effective_date=date(2026, 4, 15),
    )


@pytest.mark.parametrize(
    ("loss_date", "expected_pass"),
    [
        pytest.param(date(2026, 2, 27), True, id="day_before_expiry_covered"),
        pytest.param(date(2026, 2, 28), True, id="on_expiry_covered"),
        pytest.param(date(2026, 3, 1), False, id="day_after_expiry_refused"),
    ],
)
def test_v3_treats_expiry_as_inclusive(loss_date: date, expected_pass: bool) -> None:
    outcome = evaluate_loss_before_expiry(
        notification_request(loss_date=loss_date),
        policy(expiry_date=date(2026, 2, 28)),
    )
    assert outcome.passed is expected_pass


def test_v3_refusal_carries_the_two_dates_it_compared() -> None:
    outcome = evaluate_loss_before_expiry(
        notification_request(loss_date=date(2026, 4, 2)),
        policy(expiry_date=date(2026, 2, 28)),
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-3",
        code="LOSS_AFTER_EXPIRY",
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        expiry_date=date(2026, 2, 28),
    )


@pytest.mark.parametrize(
    ("estimated_amount", "expected_pass"),
    [
        pytest.param(Decimal("49999.99"), True, id="one_cent_below_limit_within_cover"),
        pytest.param(Decimal("50000.00"), True, id="equal_to_limit_within_cover"),
        pytest.param(Decimal("50000.01"), False, id="one_cent_above_limit_refused"),
    ],
)
def test_v4_treats_the_limit_as_inclusive(
    estimated_amount: Decimal, expected_pass: bool
) -> None:
    outcome = evaluate_amount_within_limit(
        notification_request(estimated_amount=estimated_amount),
        policy(limit=Decimal("50000.00")),
    )
    assert outcome.passed is expected_pass


def test_v4_refusal_carries_the_amount_and_the_limit() -> None:
    outcome = evaluate_amount_within_limit(
        notification_request(estimated_amount=Decimal("26000.00")),
        policy(limit=Decimal("10000.00")),
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-4",
        code="AMOUNT_EXCEEDS_LIMIT",
        policy_number="MOT-4471",
        estimated_amount=Decimal("26000.00"),
        limit=Decimal("10000.00"),
    )


@pytest.mark.parametrize(
    ("claim_type", "expected_pass"),
    [
        pytest.param("theft", True, id="theft_permitted_on_named_perils"),
        pytest.param("glass", True, id="glass_permitted_on_named_perils"),
        pytest.param("weather", True, id="weather_permitted_on_named_perils"),
        pytest.param("liability", True, id="liability_permitted_on_named_perils"),
        pytest.param("collision", False, id="collision_not_permitted_on_named_perils"),
    ],
)
def test_v5_compares_claim_type_against_the_products_permitted_subset(
    claim_type: ClaimType, expected_pass: bool
) -> None:
    outcome = evaluate_claim_type_covered(
        notification_request(claim_type=claim_type),
        policy(
            product="personal_auto_named_perils",
            permitted_claim_types=("theft", "glass", "weather", "liability"),
        ),
    )
    assert outcome.passed is expected_pass


def test_v5_refusal_names_the_product_and_its_permitted_types() -> None:
    outcome = evaluate_claim_type_covered(
        notification_request(claim_type="collision"),
        policy(
            product="personal_auto_liability_only",
            permitted_claim_types=("liability",),
        ),
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-5",
        code="TYPE_NOT_COVERED",
        policy_number="MOT-4471",
        claim_type="collision",
        permitted_claim_types=("liability",),
        product="personal_auto_liability_only",
    )


@pytest.mark.parametrize(
    ("loss_date", "expected_pass"),
    [
        pytest.param(date(2026, 1, 14), True, id="day_before_cancellation_covered"),
        pytest.param(date(2026, 1, 15), False, id="on_cancellation_date_refused"),
        pytest.param(date(2026, 1, 16), False, id="day_after_cancellation_refused"),
    ],
)
def test_v7_is_strict_on_the_cancellation_date(
    loss_date: date, expected_pass: bool
) -> None:
    """WI-0158 AC-2: the last covered day is the day before cancellation."""
    outcome = evaluate_policy_not_cancelled(
        notification_request(loss_date=loss_date),
        policy(cancellation_date=date(2026, 1, 15)),
    )
    assert outcome.passed is expected_pass


def test_v7_does_not_apply_where_the_policy_was_never_cancelled() -> None:
    """WI-0158 AC-3: null is the only representation of not cancelled."""
    outcome = evaluate_policy_not_cancelled(
        notification_request(loss_date=date(2026, 6, 4)),
        policy(cancellation_date=None),
    )
    assert outcome.passed


def test_v7_refuses_a_cancelled_policy_without_reading_expiry_date() -> None:
    """The refusal names the cancellation, not the term the policy never ran to."""
    outcome = evaluate_policy_not_cancelled(
        notification_request(loss_date=date(2026, 1, 8)),
        policy(
            effective_date=date(2025, 1, 1),
            expiry_date=date(2025, 12, 31),
            cancellation_date=date(2025, 10, 1),
        ),
    )
    assert outcome == ValidationOutcome.failed(
        rule="V-7",
        code="POLICY_CANCELLED",
        policy_number="MOT-4471",
        loss_date=date(2026, 1, 8),
        cancellation_date=date(2025, 10, 1),
    )
    assert "expiry_date" not in outcome.detail


def test_v6_passes_where_nothing_has_been_recorded(
    repository: NotificationRepository,
) -> None:
    outcome = evaluate_not_duplicate(notification_request(), repository)
    assert outcome.passed


def test_v6_refusal_carries_the_reference_of_the_existing_record(
    repository: NotificationRepository,
) -> None:
    """WI-0151 AC-2: the reference belongs to the earlier record."""
    recorded = repository.record(notification_request())
    outcome = evaluate_not_duplicate(notification_request(), repository)
    assert outcome == ValidationOutcome.failed(
        rule="V-6",
        code="DUPLICATE_NOTIFICATION",
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        claim_reference=recorded.claim_reference,
    )


def test_v6_ignores_a_difference_in_amount(repository: NotificationRepository) -> None:
    repository.record(notification_request(estimated_amount=Decimal("100.00")))
    outcome = evaluate_not_duplicate(
        notification_request(estimated_amount=Decimal("9999.00")), repository
    )
    assert outcome.code == "DUPLICATE_NOTIFICATION"


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param("MOT-4472", date(2026, 4, 2), "collision", id="only_policy_differs"),
        pytest.param("MOT-4471", date(2026, 5, 1), "collision", id="only_loss_date_differs"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="only_claim_type_differs"),
    ],
)
def test_v6_requires_all_three_fields_to_agree(
    repository: NotificationRepository,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    repository.record(notification_request())
    outcome = evaluate_not_duplicate(
        notification_request(
            policy_number=policy_number,
            loss_date=loss_date,
            claim_type=claim_type,
        ),
        repository,
    )
    assert outcome.passed


@pytest.mark.parametrize(
    ("payload_id", "expected_rule", "expected_code"),
    [
        pytest.param("EDGE-04", "V-7", "POLICY_CANCELLED", id="EDGE-04_cancelled"),
        pytest.param("EDGE-05", "V-2", "LOSS_BEFORE_INCEPTION", id="EDGE-05_inception"),
        pytest.param("EDGE-06", "V-4", "AMOUNT_EXCEEDS_LIMIT", id="EDGE-06_over_limit"),
        pytest.param("EDGE-07", "V-1", "POLICY_NOT_FOUND", id="EDGE-07_lowercase_policy"),
        pytest.param("EDGE-09", "V-5", "TYPE_NOT_COVERED", id="EDGE-09_type_not_covered"),
        pytest.param("EDGE-10", "V-7", "POLICY_CANCELLED", id="EDGE-10_cancelled_and_expired"),
    ],
)
def test_edge_payloads_are_refused_by_the_rule_the_triage_records(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
    expected_rule: str,
    expected_code: str,
) -> None:
    outcome = evaluate_notification(
        request_from(payload(payload_id)), policy_client, repository
    )
    assert not outcome.passed
    assert outcome.rule == expected_rule
    assert outcome.code == expected_code


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("EDGE-01", id="EDGE-01_loss_on_inception"),
        pytest.param("EDGE-02", id="EDGE-02_amount_equals_limit"),
        pytest.param("EDGE-03", id="EDGE-03_loss_on_expiry"),
    ],
)
def test_edge_payloads_on_an_inclusive_boundary_pass_every_rule(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
) -> None:
    outcome = evaluate_notification(
        request_from(payload(payload_id)), policy_client, repository
    )
    assert outcome.passed


def test_stage_3_precedes_stage_4_so_inception_is_reported_before_the_limit(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """EDGE-05 violates V-2 and V-4. Section 4.1 puts V-2 in the earlier stage."""
    outcome = evaluate_notification(
        request_from(payload("EDGE-05")), policy_client, repository
    )
    assert outcome.code == "LOSS_BEFORE_INCEPTION"


def test_stage_2_precedes_stage_3_so_cancellation_is_reported_before_expiry(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """EDGE-10 violates V-7 and V-3 together. WI-0158 AC-4 requires POLICY_CANCELLED."""
    outcome = evaluate_notification(
        request_from(payload("EDGE-10")), policy_client, repository
    )
    assert outcome.code == "POLICY_CANCELLED"
    assert outcome.detail["cancellation_date"] == date(2025, 10, 1)


def test_a_refusal_is_carried_as_a_rule_failure_not_as_two_loose_strings(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """The value type exists to stop a transposition, so refusals must go through it.

    `rule` and `code` are derived from `failure`, which is what makes the swap a
    type error on the path that actually produces refusals rather than only on a
    type nothing constructs.
    """
    outcome = evaluate_notification(
        request_from(payload("INVALID-07")), policy_client, repository
    )
    assert outcome.failure == RuleFailure(rule="V-7", code="POLICY_CANCELLED")
    assert (outcome.rule, outcome.code) == ("V-7", "POLICY_CANCELLED")


def test_a_passing_outcome_carries_no_rule_failure(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    outcome = evaluate_notification(
        request_from(payload("VALID-01")), policy_client, repository
    )
    assert outcome.passed
    assert outcome.failure is None
    assert (outcome.rule, outcome.code) == (None, None)


def test_stage_1_short_circuits_so_no_policy_field_is_compared(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """WI-0142 AC-4: a policy the master does not hold is not evaluated further."""
    outcome = evaluate_notification(
        request_from(payload("EDGE-07")), policy_client, repository
    )
    assert outcome.code == "POLICY_NOT_FOUND"
    assert outcome.detail == {"policy_number": "mot-4471"}


@pytest.mark.parametrize(
    ("payload_id", "expected_code"),
    [
        pytest.param("INVALID-01", "POLICY_NOT_FOUND", id="INVALID-01_policy_not_found"),
        pytest.param("INVALID-02", "LOSS_BEFORE_INCEPTION", id="INVALID-02_before_inception"),
        pytest.param("INVALID-03", "LOSS_AFTER_EXPIRY", id="INVALID-03_after_expiry"),
        pytest.param("INVALID-04", "AMOUNT_EXCEEDS_LIMIT", id="INVALID-04_over_limit"),
        pytest.param("INVALID-05", "TYPE_NOT_COVERED", id="INVALID-05_type_not_covered"),
        pytest.param("INVALID-07", "POLICY_CANCELLED", id="INVALID-07_cancelled"),
    ],
)
def test_invalid_payloads_are_refused_by_the_expected_rule(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
    expected_code: str,
) -> None:
    outcome = evaluate_notification(
        request_from(payload(payload_id)), policy_client, repository
    )
    assert outcome.code == expected_code


def test_invalid_06_is_a_duplicate_only_once_valid_01_has_been_recorded(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """The INVALID-06 context: it duplicates VALID-01, which must be recorded first."""
    first = submit_notification(
        request_from(payload("VALID-01")), policy_client, repository
    )
    assert isinstance(first, ClaimRecord)
    outcome = evaluate_notification(
        request_from(payload("INVALID-06")), policy_client, repository
    )
    assert outcome.code == "DUPLICATE_NOTIFICATION"
    assert outcome.detail["claim_reference"] == first.claim_reference


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("VALID-01", id="VALID-01"),
        pytest.param("VALID-02", id="VALID-02"),
        pytest.param("VALID-03", id="VALID-03"),
        pytest.param("VALID-04", id="VALID-04"),
        pytest.param("VALID-05", id="VALID-05"),
        pytest.param("VALID-06", id="VALID-06_description_absent"),
        pytest.param("VALID-07", id="VALID-07"),
        pytest.param("VALID-08", id="VALID-08"),
    ],
)
def test_valid_payloads_pass_every_rule(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
) -> None:
    outcome = evaluate_notification(
        request_from(payload(payload_id)), policy_client, repository
    )
    assert outcome.passed


def test_submit_records_a_notification_that_passed_every_rule(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    request = request_from(payload("VALID-01"))
    result = submit_notification(request, policy_client, repository)
    assert isinstance(result, ClaimRecord)
    assert repository.find_matching(
        request.policy_number, request.loss_date, request.claim_type
    ) is result


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("EDGE-04", id="EDGE-04_cancelled"),
        pytest.param("EDGE-05", id="EDGE-05_before_inception"),
        pytest.param("EDGE-06", id="EDGE-06_over_limit"),
        pytest.param("EDGE-07", id="EDGE-07_policy_not_found"),
        pytest.param("EDGE-09", id="EDGE-09_type_not_covered"),
    ],
)
def test_submit_records_nothing_for_a_refused_notification(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
) -> None:
    """Section 3: either a notification exists with a reference, or nothing was written."""
    request = request_from(payload(payload_id))
    result = submit_notification(request, policy_client, repository)
    assert isinstance(result, ValidationOutcome)
    assert repository.find_matching(
        request.policy_number, request.loss_date, request.claim_type
    ) is None


def test_a_refused_notification_is_not_a_duplicate_when_resubmitted(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    """WI-0151 AC-3: nothing was recorded, so there is nothing to duplicate."""
    refused = request_from(payload("EDGE-06"))
    first = submit_notification(refused, policy_client, repository)
    second = submit_notification(refused, policy_client, repository)
    assert isinstance(first, ValidationOutcome)
    assert isinstance(second, ValidationOutcome)
    assert second.code == first.code == "AMOUNT_EXCEEDS_LIMIT"


def test_submit_does_not_absorb_a_lookup_failure(
    repository: NotificationRepository,
) -> None:
    with pytest.raises(PolicyLookupFailed):
        submit_notification(
            notification_request(), StubPolicyClient(fail_with="timeout"), repository
        )


@pytest.mark.parametrize(
    ("payload_id", "expected_detail_keys"),
    [
        pytest.param(
            "EDGE-07",
            {"policy_number"},
            id="POLICY_NOT_FOUND_detail_keys",
        ),
        pytest.param(
            "EDGE-05",
            {"policy_number", "loss_date", "effective_date"},
            id="LOSS_BEFORE_INCEPTION_detail_keys",
        ),
        pytest.param(
            "INVALID-03",
            {"policy_number", "loss_date", "expiry_date"},
            id="LOSS_AFTER_EXPIRY_detail_keys",
        ),
        pytest.param(
            "EDGE-06",
            {"policy_number", "estimated_amount", "limit"},
            id="AMOUNT_EXCEEDS_LIMIT_detail_keys",
        ),
        pytest.param(
            "EDGE-09",
            {"policy_number", "claim_type", "permitted_claim_types", "product"},
            id="TYPE_NOT_COVERED_detail_keys",
        ),
        pytest.param(
            "EDGE-04",
            {"policy_number", "loss_date", "cancellation_date"},
            id="POLICY_CANCELLED_detail_keys",
        ),
    ],
)
def test_refusal_detail_carries_the_keys_section_6_documents(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    payload_id: str,
    expected_detail_keys: set[str],
) -> None:
    outcome = evaluate_notification(
        request_from(payload(payload_id)), policy_client, repository
    )
    assert set(outcome.detail) == expected_detail_keys


def test_duplicate_refusal_detail_carries_the_keys_section_6_documents(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    submit_notification(
        request_from(payload("VALID-01")), policy_client, repository
    )
    outcome = evaluate_notification(
        request_from(payload("VALID-01")), policy_client, repository
    )
    assert set(outcome.detail) == {
        "policy_number",
        "loss_date",
        "claim_type",
        "claim_reference",
    }
