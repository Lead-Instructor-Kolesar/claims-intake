"""Unit tests for the request and policy boundary models.

Names use contract vocabulary: V-0, SCHEMA_INVALID constraints, and the field
names in section 2.2. A payload that raises here never reaches a rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import BaseModel, ValidationError

from claims.models import (
    CONTRACT_ERROR_CODES,
    ClaimRecord,
    NotificationRequest,
    Policy,
    RuleFailure,
)
from claims.policy_client import StubPolicyClient
from tests.payloads import payload

type ModelOutcome = Literal["rejected", "survives"]


def _well_formed_wire() -> dict[str, object]:
    """A section 2.2 payload that V-0 accepts. Copied on every call."""
    return {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }


def _wire(**overrides: object) -> dict[str, object]:
    wire = _well_formed_wire()
    wire.update(overrides)
    return wire


def _wire_without(field: str, **overrides: object) -> dict[str, object]:
    wire = _wire(**overrides)
    del wire[field]
    return wire


def _field_from_errors(error: ValidationError) -> set[object]:
    return {loc for err in error.errors() for loc in err["loc"]}


def test_notification_request_parses_loss_date_as_date_and_amount_as_decimal() -> None:
    request = NotificationRequest.model_validate(_well_formed_wire())
    assert request.loss_date == date(2026, 4, 2)
    assert type(request.loss_date) is date
    assert request.estimated_amount == Decimal("4200.00")
    assert type(request.estimated_amount) is Decimal


@pytest.mark.parametrize(
    "wire",
    [
        pytest.param(_wire_without("description"), id="description_absent"),
        pytest.param(_wire(description=None), id="description_null"),
        pytest.param(_wire(claim_type="collision"), id="claim_type_collision"),
        pytest.param(_wire(claim_type="theft"), id="claim_type_theft"),
        pytest.param(_wire(claim_type="glass"), id="claim_type_glass"),
        pytest.param(_wire(claim_type="liability"), id="claim_type_liability"),
        pytest.param(_wire(claim_type="weather"), id="claim_type_weather"),
        pytest.param(_wire(estimated_amount="0.01"), id="estimated_amount_smallest_positive"),
        pytest.param(_wire(estimated_amount="4200"), id="estimated_amount_whole_dollars"),
    ],
)
def test_notification_request_accepts_well_formed_payloads(wire: dict[str, object]) -> None:
    NotificationRequest.model_validate(wire)


@pytest.mark.parametrize(
    ("wire", "field"),
    [
        pytest.param(
            _wire(policy_holder_name="Ada"),
            "policy_holder_name",
            id="undefined_field_policy_holder_name",
        ),
        pytest.param(_wire_without("policy_number"), "policy_number", id="policy_number_absent"),
        pytest.param(_wire(policy_number=None), "policy_number", id="policy_number_null"),
        pytest.param(_wire(policy_number=""), "policy_number", id="policy_number_empty"),
        pytest.param(
            _wire(policy_number="   "),
            "policy_number",
            id="policy_number_whitespace_only",
        ),
        pytest.param(_wire(policy_number=4471), "policy_number", id="policy_number_wrong_type"),
        pytest.param(_wire_without("loss_date"), "loss_date", id="loss_date_absent"),
        pytest.param(_wire(loss_date=None), "loss_date", id="loss_date_null"),
        pytest.param(
            _wire(loss_date="02-04-2026"),
            "loss_date",
            id="loss_date_not_yyyy_mm_dd",
        ),
        pytest.param(
            _wire(loss_date="2026-02-30"),
            "loss_date",
            id="loss_date_impossible_calendar_date",
        ),
        pytest.param(_wire(loss_date=20260402), "loss_date", id="loss_date_wrong_type"),
        pytest.param(_wire_without("claim_type"), "claim_type", id="claim_type_absent"),
        pytest.param(_wire(claim_type=None), "claim_type", id="claim_type_null"),
        pytest.param(
            _wire(claim_type="flood"),
            "claim_type",
            id="claim_type_outside_vocabulary",
        ),
        pytest.param(_wire(claim_type=""), "claim_type", id="claim_type_empty"),
        pytest.param(_wire(claim_type=1), "claim_type", id="claim_type_wrong_type"),
        pytest.param(
            _wire_without("estimated_amount"),
            "estimated_amount",
            id="estimated_amount_absent",
        ),
        pytest.param(
            _wire(estimated_amount=None),
            "estimated_amount",
            id="estimated_amount_null",
        ),
        pytest.param(
            _wire(estimated_amount="3499.999"),
            "estimated_amount",
            id="estimated_amount_three_decimal_places",
        ),
        pytest.param(_wire(estimated_amount="0"), "estimated_amount", id="estimated_amount_zero"),
        pytest.param(
            _wire(estimated_amount="0.00"),
            "estimated_amount",
            id="estimated_amount_zero_scale_two",
        ),
        pytest.param(
            _wire(estimated_amount="-1.00"),
            "estimated_amount",
            id="estimated_amount_negative",
        ),
        pytest.param(
            _wire(estimated_amount=["4200.00"]),
            "estimated_amount",
            id="estimated_amount_wrong_type",
        ),
        # Section 4.3: money is carried as a JSON string. A JSON number is the wrong
        # type under violation 2, because it is read as a binary float and this is
        # the operand V-4 compares against the policy limit.
        pytest.param(
            _wire(estimated_amount=4200.00),
            "estimated_amount",
            id="estimated_amount_json_float",
        ),
        pytest.param(
            _wire(estimated_amount=4200),
            "estimated_amount",
            id="estimated_amount_json_integer",
        ),
        pytest.param(
            _wire(estimated_amount="4.2e3"),
            "estimated_amount",
            id="estimated_amount_not_a_decimal_numeral",
        ),
        pytest.param(
            _wire(estimated_amount="4,200.00"),
            "estimated_amount",
            id="estimated_amount_grouped_thousands",
        ),
        pytest.param(_wire(description=1), "description", id="description_wrong_type"),
    ],
)
def test_notification_request_rejects_payload_that_fails_v0(
    wire: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        NotificationRequest.model_validate(wire)
    assert field in _field_from_errors(exc_info.value)


@pytest.mark.parametrize(
    ("payload_id", "outcome"),
    [
        pytest.param("EDGE-01", "survives", id="EDGE-01_loss_on_inception_survives"),
        pytest.param("EDGE-02", "survives", id="EDGE-02_amount_equals_limit_survives"),
        pytest.param("EDGE-03", "survives", id="EDGE-03_loss_on_expiry_survives"),
        pytest.param("EDGE-04", "survives", id="EDGE-04_loss_on_cancellation_survives"),
        pytest.param("EDGE-05", "survives", id="EDGE-05_before_inception_and_over_limit_survives"),
        pytest.param("EDGE-06", "survives", id="EDGE-06_amount_exceeds_limit_survives"),
        pytest.param("EDGE-07", "survives", id="EDGE-07_lowercase_policy_number_survives"),
        pytest.param("EDGE-08", "rejected", id="EDGE-08_estimated_amount_absent_fails_v0"),
        pytest.param("EDGE-09", "survives", id="EDGE-09_type_not_covered_survives"),
        pytest.param("EDGE-10", "survives", id="EDGE-10_cancelled_and_after_expiry_survives"),
        pytest.param("EDGE-11", "rejected", id="EDGE-11_claim_type_flood_fails_v0"),
        pytest.param("EDGE-12", "rejected", id="EDGE-12_amount_three_places_fails_v0"),
    ],
)
def test_edge_payloads_fail_at_model_or_survive_to_rules(
    payload_id: str, outcome: ModelOutcome
) -> None:
    if outcome == "survives":
        NotificationRequest.model_validate(payload(payload_id))
        return
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload(payload_id))


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("INVALID-01", id="INVALID-01_policy_not_found_survives"),
        pytest.param("INVALID-02", id="INVALID-02_loss_before_inception_survives"),
        pytest.param("INVALID-03", id="INVALID-03_loss_after_expiry_survives"),
        pytest.param("INVALID-04", id="INVALID-04_amount_exceeds_limit_survives"),
        pytest.param("INVALID-05", id="INVALID-05_type_not_covered_survives"),
        pytest.param("INVALID-06", id="INVALID-06_duplicate_notification_survives"),
        pytest.param("INVALID-07", id="INVALID-07_policy_cancelled_survives"),
    ],
)
def test_invalid_payloads_are_well_formed_and_survive_to_rules(payload_id: str) -> None:
    NotificationRequest.model_validate(payload(payload_id))


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
def test_valid_payloads_parse_as_notification_requests(payload_id: str) -> None:
    NotificationRequest.model_validate(payload(payload_id))


def _well_formed_policy() -> dict[str, object]:
    return {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
    }


def _policy(**overrides: object) -> dict[str, object]:
    record = _well_formed_policy()
    record.update(overrides)
    return record


def _policy_without(field: str) -> dict[str, object]:
    record = _well_formed_policy()
    del record[field]
    return record


def test_policy_treats_null_cancellation_date_as_not_cancelled() -> None:
    """WI-0158 AC-3: null is the only representation of not cancelled."""
    policy = Policy.model_validate(_well_formed_policy())
    assert policy.cancellation_date is None
    assert policy.effective_date == date(2026, 3, 1)
    assert policy.expiry_date == date(2027, 2, 28)
    assert type(policy.limit) is Decimal
    assert policy.limit == Decimal("50000.00")


def test_policy_accepts_a_present_cancellation_date() -> None:
    policy = Policy.model_validate(_policy(cancellation_date=date(2026, 1, 15)))
    assert policy.cancellation_date == date(2026, 1, 15)


@pytest.mark.parametrize(
    ("record", "field"),
    [
        pytest.param(
            _policy_without("cancellation_date"),
            "cancellation_date",
            id="cancellation_date_omitted",
        ),
        pytest.param(_policy_without("policy_number"), "policy_number", id="policy_number_absent"),
        pytest.param(_policy(policy_number=""), "policy_number", id="policy_number_empty"),
        pytest.param(
            _policy(policy_number="   "),
            "policy_number",
            id="policy_number_whitespace_only",
        ),
        pytest.param(_policy(policy_number=4471), "policy_number", id="policy_number_wrong_type"),
        pytest.param(_policy_without("product"), "product", id="product_absent"),
        pytest.param(_policy(product=None), "product", id="product_null"),
        pytest.param(
            _policy_without("effective_date"),
            "effective_date",
            id="effective_date_absent",
        ),
        pytest.param(_policy(effective_date=None), "effective_date", id="effective_date_null"),
        pytest.param(
            _policy(effective_date="not-a-date"),
            "effective_date",
            id="effective_date_wrong_type",
        ),
        pytest.param(_policy_without("expiry_date"), "expiry_date", id="expiry_date_absent"),
        pytest.param(_policy(expiry_date=None), "expiry_date", id="expiry_date_null"),
        pytest.param(
            _policy(cancellation_date="2026-02-30"),
            "cancellation_date",
            id="cancellation_date_impossible_calendar_date",
        ),
        pytest.param(_policy_without("limit"), "limit", id="limit_absent"),
        pytest.param(_policy(limit=None), "limit", id="limit_null"),
        pytest.param(_policy(limit="not-money"), "limit", id="limit_wrong_type"),
        # Section 4.3 fixes money as a JSON string on both sides of the V-4
        # comparison, so a master sending a number has broken its own record shape.
        pytest.param(_policy(limit=50000.00), "limit", id="limit_json_float"),
        pytest.param(_policy(limit=50000), "limit", id="limit_json_integer"),
        pytest.param(
            _policy_without("permitted_claim_types"),
            "permitted_claim_types",
            id="permitted_claim_types_absent",
        ),
        pytest.param(
            _policy(permitted_claim_types=("flood",)),
            "permitted_claim_types",
            id="permitted_claim_types_outside_vocabulary",
        ),
        pytest.param(
            _policy(permitted_claim_types="collision"),
            "permitted_claim_types",
            id="permitted_claim_types_wrong_type",
        ),
        pytest.param(_policy(endorsement="storm"), "endorsement", id="undefined_field"),
    ],
)
def test_policy_rejects_structurally_invalid_records(
    record: dict[str, object], field: str
) -> None:
    """A record the service cannot use is a POLICY_MASTER_INVALID_RESPONSE, not a rule failure."""
    with pytest.raises(ValidationError) as exc_info:
        Policy.model_validate(record)
    assert field in _field_from_errors(exc_info.value)


@pytest.mark.parametrize(
    "policy_number",
    [
        pytest.param("MOT-4471", id="uncancelled_policy_from_master"),
        pytest.param("MOT-4497", id="cancelled_policy_from_master"),
    ],
)
def test_policy_from_record_preserves_master_dates_and_limit(
    policy_client: StubPolicyClient, policy_number: str
) -> None:
    record = policy_client.get_policy(policy_number)
    policy = Policy.from_record(record)
    assert policy.policy_number == record.policy_number
    assert policy.effective_date == record.effective_date
    assert policy.expiry_date == record.expiry_date
    assert policy.cancellation_date == record.cancellation_date
    assert policy.limit == record.limit
    assert type(policy.effective_date) is date
    assert type(policy.limit) is Decimal


def _claim_record() -> ClaimRecord:
    return ClaimRecord(
        claim_reference="CLM-2026-000317",
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )


@pytest.mark.parametrize(
    ("build", "field"),
    [
        pytest.param(
            lambda: NotificationRequest.model_validate(_well_formed_wire()),
            "policy_number",
            id="notification_request_is_frozen",
        ),
        pytest.param(
            lambda: Policy.model_validate(_well_formed_policy()),
            "cancellation_date",
            id="policy_is_frozen",
        ),
        pytest.param(
            _claim_record,
            "claim_reference",
            id="claim_record_is_frozen",
        ),
    ],
)
def test_boundary_models_cannot_be_edited_after_parsing(
    build: Callable[[], BaseModel], field: str
) -> None:
    """A parsed request is evidence of what the caller sent, so nothing may rewrite it."""
    model = build()
    with pytest.raises(ValidationError):
        setattr(model, field, None)


def test_rule_failure_is_immutable() -> None:
    failure = RuleFailure(rule="V-7", code="POLICY_CANCELLED")
    replaced = replace(failure, code="LOSS_AFTER_EXPIRY")
    assert failure.code == "POLICY_CANCELLED"
    assert replaced.code == "LOSS_AFTER_EXPIRY"
    with pytest.raises(FrozenInstanceError):
        field_name = "code"
        setattr(failure, field_name, "LOSS_AFTER_EXPIRY")


def test_rule_failure_carries_rule_identifier_and_error_code_separately() -> None:
    """The two fields have different types, so the swapped construction

    `RuleFailure(rule="POLICY_CANCELLED", code="V-6")` is rejected by mypy rather
    than by a test. That guarantee is checked by running the type checker, which
    is why there is no runtime case for it here.
    """
    failure = RuleFailure(rule="V-6", code="DUPLICATE_NOTIFICATION")
    assert failure.rule == "V-6"
    assert failure.code == "DUPLICATE_NOTIFICATION"


def test_every_error_code_rule_failure_can_carry_is_in_contract_section_6() -> None:
    """The ErrorCode type is the section 6 enumeration, so nothing else is constructible."""
    assert "POLICY_CANCELLED" in CONTRACT_ERROR_CODES
    assert len(CONTRACT_ERROR_CODES) == len(set(CONTRACT_ERROR_CODES))


@pytest.mark.parametrize(
    "claim_reference",
    [
        pytest.param("CLM-26-000317", id="year_not_four_digits"),
        pytest.param("CLM-2026-317", id="sequence_not_six_digits"),
        pytest.param("clm-2026-000317", id="prefix_not_uppercase"),
        pytest.param("CLM-2026-000317-X", id="trailing_suffix"),
    ],
)
def test_claim_record_rejects_claim_reference_outside_section_3(
    claim_reference: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClaimRecord(
            claim_reference=claim_reference,
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
        )
    assert "claim_reference" in _field_from_errors(exc_info.value)


def test_claim_record_accepts_section_3_claim_reference() -> None:
    recorded = ClaimRecord(
        claim_reference="CLM-2026-000317",
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )
    assert recorded.claim_reference == "CLM-2026-000317"
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.estimated_amount == Decimal("4200.00")
