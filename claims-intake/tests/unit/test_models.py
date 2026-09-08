"""Tests for the boundary models against `docs/api-contract.md` sections 2 and 3."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
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
    RuleId,
)
from claims.policy_client import StubPolicyClient

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

MODEL_FAILURE_IDS = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})


def _payload(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    data.update(changes)
    return data


def _without(field: str) -> dict[str, object]:
    data = _payload()
    del data[field]
    return data


def _load_items(filename: str) -> list[dict[str, Any]]:
    raw = json.loads((DATA_DIR / filename).read_text())
    assert isinstance(raw, list)
    return raw


def _item_cases(filename: str) -> list[Any]:
    return [
        pytest.param(item["payload"], item["id"] in MODEL_FAILURE_IDS, id=str(item["id"]))
        for item in _load_items(filename)
    ]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(item["payload"], id=str(item["id"]))
        for item in _load_items("fnol_valid.json")
    ],
)
def test_accepts_valid_payloads(payload: dict[str, Any]) -> None:
    notification = NotificationRequest.model_validate(payload)
    assert isinstance(notification.loss_date, date)
    assert not isinstance(notification.loss_date, datetime)
    assert isinstance(notification.estimated_amount, Decimal)
    assert notification.estimated_amount > 0


def test_absent_and_null_description_are_equivalent() -> None:
    absent = NotificationRequest.model_validate(_without("description"))
    explicit_null = NotificationRequest.model_validate(_payload(description=None))
    assert absent.description is None
    assert explicit_null.description is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_without("policy_number"), id="missing_policy_number"),
        pytest.param(_payload(policy_number=""), id="empty_policy_number"),
        pytest.param(_without("loss_date"), id="missing_loss_date"),
        pytest.param(_payload(loss_date="04/02/2026"), id="loss_date_wrong_format"),
        pytest.param(_payload(loss_date="2026-04-02T00:00:00"), id="loss_date_datetime_string"),
        pytest.param(
            _payload(loss_date=datetime(2026, 4, 2, tzinfo=UTC)),
            id="loss_date_datetime_value",
        ),
        pytest.param(_without("claim_type"), id="missing_claim_type"),
        pytest.param(_payload(claim_type=""), id="empty_claim_type"),
        pytest.param(_payload(claim_type="flood"), id="claim_type_not_in_vocabulary"),
        pytest.param(_payload(claim_type="Collision"), id="claim_type_wrong_case"),
        pytest.param(_without("estimated_amount"), id="missing_estimated_amount"),
        pytest.param(_payload(estimated_amount="0.00"), id="estimated_amount_zero"),
        pytest.param(_payload(estimated_amount="-1.00"), id="estimated_amount_negative"),
        pytest.param(
            _payload(estimated_amount="3499.999"),
            id="estimated_amount_three_decimal_places",
        ),
        pytest.param(_payload(estimated_amount=4200.00), id="estimated_amount_float"),
        pytest.param(_payload(estimated_amount="four thousand"), id="estimated_amount_not_decimal"),
        pytest.param(
            _payload() | {"handler_note": "not a contract field"},
            id="undeclared_field",
        ),
    ],
)
def test_rejects_structurally_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "fails_at_model"),
    [
        *_item_cases("fnol_invalid.json"),
        *_item_cases("fnol_edge.json"),
    ],
)
def test_invalid_and_edge_payloads_fail_at_model_or_survive_to_rules(
    payload: dict[str, Any],
    fails_at_model: bool,
) -> None:
    """EDGE-08, EDGE-11, and EDGE-12 fail here. Every other fixture is well formed."""
    if fails_at_model:
        with pytest.raises(ValidationError):
            NotificationRequest.model_validate(payload)
    else:
        NotificationRequest.model_validate(payload)


def test_policy_requires_cancellation_date() -> None:
    """No default. Forgetting the field cannot be read as 'not cancelled' (WI-0158 AC-3)."""
    with pytest.raises(ValidationError):
        Policy.model_validate(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": ("collision",),
            }
        )


def test_policy_accepts_null_cancellation_date(policy_client: StubPolicyClient) -> None:
    record = policy_client.get_policy("MOT-4471")
    policy = Policy.model_validate(record)
    assert policy.cancellation_date is None
    assert policy.effective_date == date(2026, 3, 1)
    assert policy.limit == Decimal("50000.00")


def test_policy_preserves_cancellation_date(policy_client: StubPolicyClient) -> None:
    record = policy_client.get_policy("MOT-4496")
    policy = Policy.model_validate(record)
    assert policy.cancellation_date == date(2026, 2, 1)


def test_rule_failure_is_immutable() -> None:
    failure = RuleFailure(rule=RuleId.V2, code=ErrorCode.LOSS_BEFORE_INCEPTION)
    with pytest.raises(ValidationError):
        failure.rule = RuleId.V1


def test_rule_failure_rejects_swapped_identifier_and_code() -> None:
    with pytest.raises(ValidationError):
        RuleFailure.model_validate(
            {"rule": ErrorCode.POLICY_NOT_FOUND, "code": RuleId.V1}
        )


def test_recorded_notification_requires_contract_reference_format() -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(
            claim_reference="CLM-1",
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
        )
