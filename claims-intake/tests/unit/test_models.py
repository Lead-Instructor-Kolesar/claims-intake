from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import ValidationError

from claims.models import *


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
            },
            id="complete",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
            },
            id="no_description",
        ),
    ],
)
def test_notification_request_accepts(body: dict[str, Any]) -> None:
    NotificationRequest(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
            },
            id="missing_loss_date",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
            },
            id="missing_claim_type",
        ),
    ],
)
def test_notification_request_refuses_missing_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest(**body)



@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
                "extra": "nope"
            },
            id="extra_field",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
                "new": 1234,
            },
            id="description_field_replaced_with_new_field",
        ),
    ],
)
def test_notification_request_refuses_extra_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest(**body)



@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
            },
            id="empty_policy_number",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026/04/02",
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
            },
            id="incorrect_date_format",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "flood",
                "estimated_amount": Decimal("4200.00"),
                "description": "Rear ended at a junction.",
            },
            id="claim_type_not_in_vocabulary",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("4200.00113"),
                "description": "Rear ended at a junction.",
            },
            id="estimated_amount_decimal_place_gt_2",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("0.00"),
                "description": "Rear ended at a junction.",
            },
            id="estimated_amount_is_zero",
        )
    ],
)
def test_notification_request_refuses_invalid_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest(**body)

@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="complete",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": None,
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="no_cancellation_date",
        ),
    ],
)
def test_policy_accepts(body: dict[str, Any]) -> None:
    Policy(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "product": "personal_auto_standard",
                "effective_date": date(2027, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft"),
            },
            id="missing_policy_number",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "expiry_date": date(2027, 2, 28),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft"),
            },
            id="missing_effective_date",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "expiry_date": date(2027, 2, 28),
                "limit": "50000.00",
                "permitted_claim_types": ("collision", "theft"),
            },
            id="limit_is_string",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "expiry_date": date(2027, 2, 28),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", 123),
            },
            id="permitted_claim_type_is_integer",
        ),
    ],
)
def test_policy_refuses_missing_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Policy(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft"),
                "extra": "nope",
            },
            id="extra_field",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "new": 1234,
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft"),
            },
            id="cancellation_date_replaced_with_new_field",
        ),
    ],
)
def test_policy_refuses_extra_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Policy(**body)

@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="policy_number_empty",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="product_empty",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": "2026/03/01",
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="effective_date_format_invalid",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": "invalid",
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="expiry_date_format_invalid",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": 123,
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="cancellation_date_format_invalid",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.12345"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="limit_decimal_place_gt_2",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("0.00"),
                "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
            },
            id="limit_decimal_zero",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": (123, 456),
            },
            id="permitted_claim_types_contains_integer",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "cancellation_date": date(2027, 2, 20),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision", "flood"),
            },
            id="permitted_claim_types_contains_invalid_input",
        ),
    ],
)
def test_policy_refuses_invalid_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Policy(**body)

@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "claim_reference": "CLM-2026-000317",
                "status": "recorded",
            },
            id="complete",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-2026-000001",
                "status": "recorded",
            },
            id="another_reference",
        ),
    ],
)
def test_recorded_notification_accepts(body: dict[str, Any]) -> None:
    RecordedNotification(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "status": "recorded",
            },
            id="missing_claim_reference",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-2026-000317",
            },
            id="missing_status",
        ),
    ],
)
def test_recorded_notification_refuses_missing_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "claim_reference": "CLM-2026-0022230001",
                "status": "recorded",
            },
            id="claim_reference_extra_padded_sequence",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-20269-0022230001",
                "status": "recorded",
            },
            id="claim_reference_year_too_long",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-20269-0022230001",
                "status": "",
            },
            id="status_empty",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-20269-0022230001",
                "status": 893,
            },
            id="status_integer",
        ),
    ],
)
def test_recorded_notification_refuses_invalid_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(**body)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "claim_reference": "CLM-2026-000317",
                "status": "recorded",
                "extra": "nope",
            },
            id="extra_field",
        ),
        pytest.param(
            {
                "claim_reference": "CLM-2026-000317",
                "new": 1234,
            },
            id="status_replaced_with_new_field",
        ),
    ],
)
def test_recorded_notification_refuses_extra_fields(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(**body)


def test_rule_failure_rejects_mutation() -> None:
    failure = RuleFailure(rule=RuleId("V-1"), code=ErrorCode("POLICY_NOT_FOUND"))
    mutable = cast(Any, failure)
    with pytest.raises(FrozenInstanceError):
        mutable.rule = RuleId("V-2")

def test_claim_record_rejects_mutation() -> None:
    test_notification = NotificationRequest(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction."
    )

    record = ClaimRecord("CLM-2026-000317", test_notification)
    mutable = cast(Any, record)
    with pytest.raises(FrozenInstanceError):
        mutable.record = "CLM-2026-000318"

@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4479",
                "loss_date": date(2026, 3, 15),
                "claim_type": "collision",
                "estimated_amount": Decimal("5000.00"),
                "description": "Loss on the day cover attaches.",
            },
            id="EDGE-01",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4501",
                "loss_date": date(2026, 6, 4),
                "claim_type": "collision",
                "estimated_amount": Decimal("50000.00"),
                "description": "Total loss valued at the policy limit.",
            },
            id="EDGE-02",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4489",
                "loss_date": date(2026, 2, 28),
                "claim_type": "theft",
                "estimated_amount": Decimal("9000.00"),
                "description": "Loss on the final day of the term.",
            },
            id="EDGE-03",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4497",
                "loss_date": date(2026, 1, 15),
                "claim_type": "glass",
                "estimated_amount": Decimal("480.00"),
                "description": "Loss on the day the cancellation takes effect.",
            },
            id="EDGE-04",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4493",
                "loss_date": date(2026, 3, 2),
                "claim_type": "collision",
                "estimated_amount": Decimal("72000.00"),
                "description": "Loss before inception and above the limit.",
            },
            id="EDGE-05",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4502",
                "loss_date": date(2026, 3, 19),
                "claim_type": "collision",
                "estimated_amount": Decimal("26000.00"),
                "description": "Above the limit on a policy whose product permits collision.",
            },
            id="EDGE-06",
        ),
        pytest.param(
            {
                "policy_number": "mot-4471",
                "loss_date": date(2026, 4, 6),
                "claim_type": "collision",
                "estimated_amount": Decimal("3300.00"),
                "description": "Policy number keyed in lower case.",
            },
            id="EDGE-07",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4481",
                "loss_date": date(2026, 3, 27),
                "claim_type": "collision",
                "estimated_amount": Decimal("4800.00"),
                "description": "Collision on a named perils product.",
            },
            id="EDGE-09",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4500",
                "loss_date": date(2026, 1, 8),
                "claim_type": "collision",
                "estimated_amount": Decimal("6000.00"),
                "description": "Loss after cancellation and after the original expiry date.",
            },
            id="EDGE-10",
        ),
    ],
)
def test_notification_request_accepts_edge_payloads(body: dict[str, Any]) -> None:
    NotificationRequest(**body)
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {
                "policy_number": "MOT-4472",
                "loss_date": date(2026, 3, 25),
                "claim_type": "theft",
                "description": "Amount omitted by the portal.",
            },
            id="EDGE-08",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": date(2026, 4, 11),
                "claim_type": "flood",
                "estimated_amount": Decimal("15000.00"),
                "description": "Claim type is not one of the values the contract defines.",
            },
            id="EDGE-11",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4476",
                "loss_date": date(2026, 4, 9),
                "claim_type": "collision",
                "estimated_amount": Decimal("3499.999"),
                "description": "Estimated amount carries three decimal places.",
            },
            id="EDGE-12",
        ),
    ],
)
def test_notification_request_refuses_edge_payloads(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest(**body)