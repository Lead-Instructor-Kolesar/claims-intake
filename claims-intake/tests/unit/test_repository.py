"""Unit tests for the in-memory notification repository.

Run:

    uv run pytest tests/unit/test_repository.py -q
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from claims.models import AdmittedNotification, NotificationRequest
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


def _admitted(**overrides: object) -> AdmittedNotification:
    return AdmittedNotification.admit(_valid_request(**overrides))


@pytest.fixture
def repo() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def admitted() -> AdmittedNotification:
    return _admitted()


def test_record_issues_claim_reference(
    repo: NotificationRepository, admitted: AdmittedNotification
) -> None:
    recorded = repo.record(admitted)
    assert recorded.claim_reference == f"CLM-{datetime.now(tz=UTC).year}-000001"
    assert recorded.status == "recorded"
    assert recorded.policy_number == "MOT-4471"
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.claim_type == "collision"
    assert recorded.estimated_amount == Decimal("4200.00")
    assert recorded.description == "Rear ended at a junction."


def test_record_increments_sequence(repo: NotificationRepository) -> None:
    first = repo.record(_admitted())
    second = repo.record(_admitted(policy_number="MOT-4472"))
    year = datetime.now(tz=UTC).year
    assert first.claim_reference == f"CLM-{year}-000001"
    assert second.claim_reference == f"CLM-{year}-000002"


def test_find_matching_returns_recorded_notification(
    repo: NotificationRepository, admitted: AdmittedNotification
) -> None:
    recorded = repo.record(admitted)
    found = repo.find_matching(admitted)
    assert found is recorded


def test_unrecorded_notification_is_not_a_duplicate(
    repo: NotificationRepository, admitted: AdmittedNotification
) -> None:
    """WI-0151 AC-3: a refused submission is never written, so it cannot match.

    record() accepts AdmittedNotification, not NotificationRequest, so a rejected
    inbound payload cannot enter the store.
    """
    assert repo.find_matching(admitted) is None


def test_find_matching_is_case_sensitive(repo: NotificationRepository) -> None:
    repo.record(_admitted(policy_number="MOT-4471"))
    assert repo.find_matching(_admitted(policy_number="mot-4471")) is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"policy_number": "MOT-0000"}, id="wrong_policy_number"),
        pytest.param({"loss_date": "2026-04-03"}, id="wrong_loss_date"),
        pytest.param({"claim_type": "theft"}, id="wrong_claim_type"),
    ],
)
def test_find_matching_requires_all_three_fields(
    repo: NotificationRepository,
    admitted: AdmittedNotification,
    overrides: dict[str, object],
) -> None:
    repo.record(admitted)
    assert repo.find_matching(_admitted(**overrides)) is None
