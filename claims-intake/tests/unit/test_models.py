"""Pin the W-* boundary so Day 3 does not re-decide request shape."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from claims.models import (
    ErrorCode,
    NotificationRequest,
    Policy,
    RecordedNotification,
    RuleFailure,
    RuleIdentifier,
    _exactly_two_decimal_places,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_named_payloads(filename: str) -> dict[str, dict[str, Any]]:
    raw = json.loads((DATA_DIR / filename).read_text())
    payloads: dict[str, dict[str, Any]] = {}
    for item in raw:
        payload = item["payload"]
        assert isinstance(payload, dict)
        payloads[str(item["id"])] = payload
    return payloads


EDGE_PAYLOADS = _load_named_payloads("fnol_edge.json")
INVALID_PAYLOADS = _load_named_payloads("fnol_invalid.json")
EDGE_FAILS_AT_MODEL = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})


def _valid_request_fields() -> dict[str, Any]:
    return {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }


def _valid_policy_fields() -> dict[str, Any]:
    return {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
    }


def _valid_record_fields() -> dict[str, Any]:
    return {
        "claim_reference": "CLM-2026-000317",
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": None,
    }


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_valid_request_fields(), id="all-section-2.2-fields"),
        pytest.param(
            {k: v for k, v in _valid_request_fields().items() if k != "description"},
            id="description-absent-equals-null",
        ),
        pytest.param(
            {**_valid_request_fields(), "description": None},
            id="description-null-equals-absent",
        ),
    ],
)
def test_notification_request_accepts_a_well_formed_body(body: dict[str, Any]) -> None:
    request = NotificationRequest.model_validate(body)
    assert request.loss_date == date(2026, 4, 2)
    assert request.estimated_amount == Decimal("4200.00")
    assert isinstance(request.loss_date, date)
    assert isinstance(request.estimated_amount, Decimal)


@pytest.mark.parametrize(
    "extra_key",
    [
        pytest.param("handler_id", id="unexpected-field-handler_id"),
        pytest.param("policyNumber", id="misspelled-policyNumber"),
        pytest.param("amount", id="misspelled-amount"),
    ],
)
def test_notification_request_rejects_a_field_not_in_section_2_2(extra_key: str) -> None:
    body = {**_valid_request_fields(), extra_key: "x"}
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param("policy_number", id="required-policy_number-absent"),
        pytest.param("loss_date", id="required-loss_date-absent"),
        pytest.param("claim_type", id="required-claim_type-absent"),
        pytest.param("estimated_amount", id="required-estimated_amount-absent-EDGE-08"),
    ],
)
def test_notification_request_rejects_a_missing_required_field(missing: str) -> None:
    body = _valid_request_fields()
    del body[missing]
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("policy_number", "", id="empty-policy_number"),
        pytest.param("policy_number", 4471, id="policy_number-wrong-type"),
        pytest.param("loss_date", "2026-13-40", id="loss_date-not-YYYY-MM-DD"),
        pytest.param("loss_date", 20260402, id="loss_date-wrong-type"),
        pytest.param("description", 1, id="description-wrong-type"),
    ],
)
def test_w1_rejects_uninterpretable_field_values(field: str, value: object) -> None:
    body = _valid_request_fields()
    body[field] = value
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "claim_type",
    [
        pytest.param("flood", id="EDGE-11-flood-not-in-vocabulary"),
        pytest.param("Collision", id="claim_type-folded-Collision"),
        pytest.param("COLLISION", id="claim_type-folded-COLLISION"),
        pytest.param("", id="empty-claim_type"),
        pytest.param("fire", id="claim_type-fire-not-in-vocabulary"),
    ],
)
def test_w2_rejects_claim_type_outside_section_2_3(claim_type: str) -> None:
    body = {**_valid_request_fields(), "claim_type": claim_type}
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "amount",
    [
        pytest.param(Decimal("3499.999"), id="EDGE-12-three-decimal-places"),
        pytest.param(3499, id="estimated_amount-scale-zero"),
        pytest.param("3499", id="estimated_amount-string-without-decimal-point"),
        pytest.param("12.3a", id="estimated_amount-string-fraction-not-digits"),
        pytest.param(True, id="estimated_amount-boolean"),
        pytest.param([], id="estimated_amount-non-scalar"),
        pytest.param(Decimal("0.00"), id="estimated_amount-not-greater-than-zero"),
        pytest.param(Decimal("-1.00"), id="estimated_amount-negative"),
        pytest.param(Decimal("0.001"), id="estimated_amount-three-places-fraction"),
    ],
)
def test_w3_rejects_estimated_amount_that_is_not_usd_to_the_cent(amount: object) -> None:
    body = {**_valid_request_fields(), "estimated_amount": amount}
    with pytest.raises((ValidationError, TypeError)):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param([0], id="unknown-type-passed-through-to-pydantic"),
    ],
)
def test_money_parser_returns_unknown_types_unchanged(value: object) -> None:
    assert _exactly_two_decimal_places(value) is value


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(EDGE_PAYLOADS["EDGE-08"], id="EDGE-08-W-1-estimated_amount-absent"),
        pytest.param(EDGE_PAYLOADS["EDGE-11"], id="EDGE-11-W-2-flood-not-in-vocabulary"),
        pytest.param(EDGE_PAYLOADS["EDGE-12"], id="EDGE-12-W-3-three-decimal-places"),
    ],
)
def test_edge_payload_fails_well_formedness(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(EDGE_PAYLOADS[payload_id], id=f"{payload_id}-survives-to-rules")
        for payload_id in EDGE_PAYLOADS
        if payload_id not in EDGE_FAILS_AT_MODEL
    ],
)
def test_edge_payload_survives_to_the_rule_table(payload: dict[str, Any]) -> None:
    NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(INVALID_PAYLOADS[payload_id], id=f"{payload_id}-survives-to-rules")
        for payload_id in INVALID_PAYLOADS
    ],
)
def test_invalid_payload_survives_to_the_rule_table(payload: dict[str, Any]) -> None:
    NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "cancellation_date",
    [
        pytest.param(None, id="WI-0158-AC-3-cancellation_date-null"),
        pytest.param(date(2026, 1, 15), id="cancellation_date-present"),
    ],
)
def test_policy_accepts_cancellation_date_null_or_a_date(
    cancellation_date: date | None,
) -> None:
    fields = _valid_policy_fields()
    fields["cancellation_date"] = cancellation_date
    policy = Policy.model_validate(fields)
    assert policy.cancellation_date == cancellation_date
    assert isinstance(policy.effective_date, date)
    assert isinstance(policy.limit, Decimal)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("underwriter", "x", id="policy-unexpected-field"),
        pytest.param("policy_number", "", id="policy-empty-policy_number"),
        pytest.param("effective_date", "15-03-2026", id="policy-effective_date-not-ISO"),
        pytest.param("expiry_date", 20270228, id="policy-expiry_date-wrong-type"),
        pytest.param("limit", Decimal("50000.001"), id="policy-limit-not-two-places"),
        pytest.param("limit", Decimal("0.00"), id="policy-limit-not-greater-than-zero"),
        pytest.param(
            "permitted_claim_types",
            ("flood",),
            id="policy-permitted-claim_types-outside-vocabulary",
        ),
    ],
)
def test_policy_rejects_constraint_violations(field: str, value: object) -> None:
    fields = _valid_policy_fields()
    fields[field] = value
    with pytest.raises(ValidationError):
        Policy.model_validate(fields)


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param("policy_number", id="policy-policy_number-absent"),
        pytest.param("product", id="policy-product-absent"),
        pytest.param("effective_date", id="policy-effective_date-absent"),
        pytest.param("expiry_date", id="policy-expiry_date-absent"),
        pytest.param("cancellation_date", id="policy-cancellation_date-absent-no-default"),
        pytest.param("limit", id="policy-limit-absent"),
        pytest.param("permitted_claim_types", id="policy-permitted_claim_types-absent"),
    ],
)
def test_policy_rejects_absent_required_fields(missing: str) -> None:
    fields = _valid_policy_fields()
    del fields[missing]
    with pytest.raises(ValidationError):
        Policy.model_validate(fields)


@pytest.mark.parametrize(
    "claim_reference",
    [
        pytest.param("CLM-2026-000317", id="section-3-example-reference"),
        pytest.param("CLM-2026-000001", id="first-sequence"),
    ],
)
def test_recorded_notification_accepts_section_3_claim_reference(
    claim_reference: str,
) -> None:
    fields = {**_valid_record_fields(), "claim_reference": claim_reference}
    record = RecordedNotification.model_validate(fields)
    assert record.loss_date == date(2026, 4, 2)
    assert record.estimated_amount == Decimal("4200.00")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("claim_reference", "CLM-26-1", id="claim_reference-wrong-pattern"),
        pytest.param("claim_reference", "CLM-2026-317", id="claim_reference-sequence-not-six"),
        pytest.param("policy_number", "", id="record-empty-policy_number"),
        pytest.param("loss_date", 20260402, id="record-loss_date-wrong-type"),
        pytest.param("claim_type", "flood", id="record-claim_type-not-in-vocabulary"),
        pytest.param("estimated_amount", Decimal("0.00"), id="record-amount-not-gt-zero"),
        pytest.param("estimated_amount", Decimal("3499.999"), id="record-amount-not-two-places"),
        pytest.param("description", 1, id="record-description-wrong-type"),
        pytest.param("extra", "x", id="record-unexpected-field"),
    ],
)
def test_recorded_notification_rejects_constraint_violations(
    field: str, value: object
) -> None:
    fields = _valid_record_fields()
    fields[field] = value
    with pytest.raises(ValidationError):
        RecordedNotification.model_validate(fields)


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param("claim_reference", id="record-claim_reference-absent"),
        pytest.param("policy_number", id="record-policy_number-absent"),
        pytest.param("loss_date", id="record-loss_date-absent"),
        pytest.param("claim_type", id="record-claim_type-absent"),
        pytest.param("estimated_amount", id="record-estimated_amount-absent"),
    ],
)
def test_recorded_notification_rejects_absent_required_fields(missing: str) -> None:
    fields = _valid_record_fields()
    del fields[missing]
    with pytest.raises(ValidationError):
        RecordedNotification.model_validate(fields)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        pytest.param("V-7", "POLICY_CANCELLED", id="V-7-POLICY_CANCELLED"),
        pytest.param("W-1", "MALFORMED_REQUEST", id="W-1-MALFORMED_REQUEST"),
        pytest.param("V-6", "DUPLICATE_NOTIFICATION", id="V-6-DUPLICATE_NOTIFICATION"),
    ],
)
def test_rule_failure_stores_rule_identifier_apart_from_code(
    rule: RuleIdentifier, code: ErrorCode
) -> None:
    failure = RuleFailure(rule=rule, code=code)
    assert failure.rule == rule
    assert failure.code == code


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("rule", id="rule-immutable"),
        pytest.param("code", id="code-immutable"),
    ],
)
def test_rule_failure_is_immutable(field: str) -> None:
    failure = RuleFailure(rule="V-1", code="POLICY_NOT_FOUND")
    with pytest.raises(FrozenInstanceError):
        setattr(failure, field, "V-2")
