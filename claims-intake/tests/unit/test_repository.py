"""Unit tests for the in-memory notification repository.

Run:

    uv run pytest tests/unit/test_repository.py -q
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from claims.models import NotificationRequest
from claims.repository import NotificationRepository


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


@pytest.fixture
def repo() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def valid_request() -> NotificationRequest:
    return _valid_request()


def test_record_issues_claim_reference(
    repo: NotificationRepository, valid_request: NotificationRequest
) -> None:
    recorded = repo.record(valid_request)
    assert recorded.claim_reference == f"CLM-{datetime.now(tz=UTC).year}-000001"
    assert recorded.status == "recorded"
    assert recorded.policy_number == "MOT-4471"
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.claim_type == "collision"
    assert recorded.estimated_amount == Decimal("4200.00")
    assert recorded.description == "Rear ended at a junction."


def test_record_increments_sequence(repo: NotificationRepository) -> None:
    first = repo.record(_valid_request())
    second = repo.record(_valid_request(policy_number="MOT-4472"))
    year = datetime.now(tz=UTC).year
    assert first.claim_reference == f"CLM-{year}-000001"
    assert second.claim_reference == f"CLM-{year}-000002"


def test_record_preserves_policy_number_case(repo: NotificationRepository) -> None:
    recorded = repo.record(_valid_request(policy_number="mot-4471"))
    assert recorded.policy_number == "mot-4471"


def test_find_matching_returns_recorded_notification(
    repo: NotificationRepository, valid_request: NotificationRequest
) -> None:
    recorded = repo.record(valid_request)
    found = repo.find_matching("MOT-4471", date(2026, 4, 2), "collision")
    assert found is recorded


def test_find_matching_returns_none_when_absent(repo: NotificationRepository) -> None:
    assert repo.find_matching("MOT-4471", date(2026, 4, 2), "collision") is None


def test_unrecorded_notification_is_not_a_duplicate(
    repo: NotificationRepository, valid_request: NotificationRequest
) -> None:
    """WI-0151 AC-3: a refused submission is never written, so it cannot match."""
    assert (
        repo.find_matching(
            valid_request.policy_number,
            valid_request.loss_date,
            valid_request.claim_type,
        )
        is None
    )


def test_find_matching_is_case_sensitive(repo: NotificationRepository) -> None:
    repo.record(_valid_request(policy_number="MOT-4471"))
    assert repo.find_matching("mot-4471", date(2026, 4, 2), "collision") is None


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param("MOT-0000", date(2026, 4, 2), "collision", id="wrong_policy_number"),
        pytest.param("MOT-4471", date(2026, 4, 3), "collision", id="wrong_loss_date"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="wrong_claim_type"),
    ],
)
def test_find_matching_requires_all_three_fields(
    repo: NotificationRepository,
    valid_request: NotificationRequest,
    policy_number: str,
    loss_date: date,
    claim_type: str,
) -> None:
    repo.record(valid_request)
    assert repo.find_matching(policy_number, loss_date, claim_type) is None
