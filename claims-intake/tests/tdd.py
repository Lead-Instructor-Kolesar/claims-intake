"""Day 2 — simple tests for models.py.

Implement one class at a time. Run:

    uv run pytest tests/tdd.py -q
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from claims.models import NotificationRequest, Policy, RecordedNotification
from claims.repository import NotificationRepository


def test_valid_notification_request() -> None:
    request = NotificationRequest.model_validate(
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
            "description": "Rear ended at a junction.",
        }
    )
    assert request.policy_number == "MOT-4471"
    assert request.loss_date == date(2026, 4, 2)
    assert request.claim_type == "collision"
    assert request.estimated_amount == Decimal("4200.00")
    assert request.description == "Rear ended at a junction."


def test_description_is_optional() -> None:
    request = NotificationRequest.model_validate(
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
        }
    )
    assert request.description is None


def test_empty_policy_number_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(
            {
                "policy_number": "",
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "estimated_amount": "4200.00",
            }
        )


def test_lowercase_policy_number_is_still_well_formed() -> None:
    """EDGE-07: case is preserved; lookup is V-1, not a shape error."""
    request = NotificationRequest.model_validate(
        {
            "policy_number": "mot-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
        }
    )
    assert request.policy_number == "mot-4471"


def test_unknown_claim_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "claim_type": "flood",
                "estimated_amount": "4200.00",
            }
        )


def test_zero_amount_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "estimated_amount": "0.00",
            }
        )


def test_more_than_two_decimal_places_is_rejected() -> None:
    """EDGE-12: do not round or truncate."""
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "estimated_amount": "3499.999",
            }
        )


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "estimated_amount": "4200.00",
                "loss_city": "Austin",
            }
        )


def test_policy_fields() -> None:
    policy = Policy(
        policy_number="MOT-4471",
        product="personal_auto_standard",
        effective_date=date(2026, 3, 1),
        expiry_date=date(2027, 2, 28),
        cancellation_date=None,
        limit=Decimal("50000.00"),
        permitted_claim_types=("collision", "theft", "glass", "liability", "weather"),
    )
    assert policy.policy_number == "MOT-4471"
    assert policy.cancellation_date is None
    assert policy.limit == Decimal("50000.00")


def test_recorded_notification_fields() -> None:
    recorded = RecordedNotification(
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


def _valid_request(**overrides: object) -> NotificationRequest:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    payload.update(overrides)
    return NotificationRequest.model_validate(payload)


def test_record_issues_claim_reference() -> None:
    repo = NotificationRepository()
    recorded = repo.record(_valid_request())
    assert recorded.claim_reference == f"CLM-{datetime.now(tz=UTC).year}-000001"
    assert recorded.status == "recorded"
    assert recorded.policy_number == "MOT-4471"
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.claim_type == "collision"
    assert recorded.estimated_amount == Decimal("4200.00")
    assert recorded.description == "Rear ended at a junction."


def test_record_increments_sequence() -> None:
    repo = NotificationRepository()
    first = repo.record(_valid_request())
    second = repo.record(_valid_request(policy_number="MOT-4472"))
    year = datetime.now(tz=UTC).year
    assert first.claim_reference == f"CLM-{year}-000001"
    assert second.claim_reference == f"CLM-{year}-000002"


def test_record_preserves_policy_number_case() -> None:
    repo = NotificationRepository()
    recorded = repo.record(_valid_request(policy_number="mot-4471"))
    assert recorded.policy_number == "mot-4471"


def test_find_matching_returns_recorded_notification() -> None:
    repo = NotificationRepository()
    recorded = repo.record(_valid_request())
    found = repo.find_matching("MOT-4471", date(2026, 4, 2), "collision")
    assert found is recorded


def test_find_matching_returns_none_when_absent() -> None:
    repo = NotificationRepository()
    assert repo.find_matching("MOT-4471", date(2026, 4, 2), "collision") is None


def test_find_matching_is_case_sensitive() -> None:
    repo = NotificationRepository()
    repo.record(_valid_request(policy_number="MOT-4471"))
    assert repo.find_matching("mot-4471", date(2026, 4, 2), "collision") is None
