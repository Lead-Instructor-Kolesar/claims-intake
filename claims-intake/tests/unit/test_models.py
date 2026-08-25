"""Unit tests for the Day 2 boundary models.

Run:

    uv run pytest tests/unit/test_models.py -q
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from claims.models import ClaimRecord, NotificationRequest, Policy, RecordedNotification

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# INVALID-01..07 and EDGE-01..07, 09, 10 are well formed: they survive the model
# and fail (or pass) at the rule table. EDGE-08, 11, 12 fail at the model (400).

MODEL_FAILURE_IDS = ("EDGE-08", "EDGE-11", "EDGE-12")
SURVIVES_TO_RULES_IDS = (
    "INVALID-01",
    "INVALID-02",
    "INVALID-03",
    "INVALID-04",
    "INVALID-05",
    "INVALID-06",
    "INVALID-07",
    "EDGE-01",
    "EDGE-02",
    "EDGE-03",
    "EDGE-04",
    "EDGE-05",
    "EDGE-06",
    "EDGE-07",
    "EDGE-09",
    "EDGE-10",
)


def _base(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    payload.update(overrides)
    return payload


def _without(*keys: str) -> dict[str, object]:
    payload = _base()
    for key in keys:
        del payload[key]
    return payload


def _fixture_payloads() -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for name in ("fnol_invalid.json", "fnol_edge.json"):
        records = json.loads((DATA_DIR / name).read_text())
        for record in records:
            payloads[record["id"]] = record["payload"]
    return payloads


def test_valid_notification_request() -> None:
    request = NotificationRequest.model_validate(_base())
    assert request.policy_number == "MOT-4471"
    assert request.loss_date == date(2026, 4, 2)
    assert request.claim_type == "collision"
    assert request.estimated_amount == Decimal("4200.00")
    assert request.description == "Rear ended at a junction."


def test_description_is_optional() -> None:
    request = NotificationRequest.model_validate(_without("description"))
    assert request.description is None


def test_lowercase_policy_number_is_still_well_formed() -> None:
    """EDGE-07: case is preserved; lookup is V-1, not a shape error."""
    request = NotificationRequest.model_validate(_base(policy_number="mot-4471"))
    assert request.policy_number == "mot-4471"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_base(policy_number=""), id="empty_policy_number"),
        pytest.param(_without("policy_number"), id="missing_policy_number"),
        pytest.param(_without("loss_date"), id="missing_loss_date"),
        pytest.param(_base(loss_date="02-04-2026"), id="unparseable_loss_date"),
        pytest.param(_base(claim_type="flood"), id="claim_type_outside_vocabulary"),
        pytest.param(_without("claim_type"), id="missing_claim_type"),
        pytest.param(_base(estimated_amount="0.00"), id="zero_amount"),
        pytest.param(_without("estimated_amount"), id="missing_amount"),
        pytest.param(_base(estimated_amount="3499.999"), id="three_decimal_places"),
        pytest.param(_base(loss_city="Austin"), id="unknown_field"),
    ],
)
def test_notification_request_rejects_malformed_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize("payload_id", MODEL_FAILURE_IDS)
def test_fixture_payloads_that_fail_at_the_model(payload_id: str) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_fixture_payloads()[payload_id])


@pytest.mark.parametrize("payload_id", SURVIVES_TO_RULES_IDS)
def test_fixture_payloads_that_survive_to_the_rules(payload_id: str) -> None:
    NotificationRequest.model_validate(_fixture_payloads()[payload_id])


def test_policy_uncancelled_when_cancellation_date_is_none() -> None:
    """WI-0158 AC-3: None means the policy was not cancelled."""
    policy = Policy(
        policy_number="MOT-4471",
        product="personal_auto_standard",
        effective_date=date(2026, 3, 1),
        expiry_date=date(2027, 2, 28),
        cancellation_date=None,
        limit=Decimal("50000.00"),
        permitted_claim_types=("collision", "theft", "glass", "liability", "weather"),
    )
    assert policy.cancellation_date is None
    assert policy.limit == Decimal("50000.00")


def test_claim_record_carries_a_claim_reference() -> None:
    recorded = ClaimRecord(
        claim_reference="CLM-2026-000317",
        status="recorded",
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )
    assert recorded.claim_reference == "CLM-2026-000317"
    assert recorded.status == "recorded"


def test_malformed_claim_reference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(
            claim_reference="CLM-26-317",
            status="recorded",
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
        )
