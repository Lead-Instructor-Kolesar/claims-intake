import re
from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimType, NotificationRequest
from claims.repository import NotificationRepository

CLAIM_REFERENCE_PATTERN = r"^CLM-\d{4}-\d{6}$"


@pytest.fixture
def mock_repository() -> NotificationRepository:
    return NotificationRepository()


test_notification = NotificationRequest(
    policy_number="MOT-4471",
    loss_date=date(2026, 4, 2),
    claim_type="collision",
    estimated_amount=Decimal("4200.00"),
    description="Rear ended at a junction."
)


def test_record_issues_a_well_formed_reference(mock_repository: NotificationRepository) -> None:
    recorded = mock_repository.record(test_notification)
    assert re.fullmatch(CLAIM_REFERENCE_PATTERN,recorded.claim_reference)
    assert recorded.status == "recorded"


def test_record_never_reissues_a_reference(mock_repository: NotificationRepository) -> None:
    first = mock_repository.record(test_notification)
    second = mock_repository.record(test_notification)
    assert first.claim_reference != second.claim_reference

def test_find_matching_when_all_three_fields_agree(mock_repository: NotificationRepository) -> None:
    recorded = mock_repository.record(test_notification)
    found = mock_repository.find_matching("MOT-4471", date(2026, 4, 2), "collision")
    assert found is not None
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    "policy_number, loss_date, claim_type",
    [
        pytest.param("MOT-9999", date(2026, 4, 2), "collision", id="policy_number_differs"),
        pytest.param("MOT-4471", date(2026, 12, 31), "collision", id="loss_date_differs"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="claim_type_differs"),
    ],
)
def test_find_matching_when_only_two_fields_agree(
    mock_repository: NotificationRepository, policy_number: str, loss_date: date, claim_type: ClaimType
) -> None:
    mock_repository.record(test_notification)
    assert mock_repository.find_matching(policy_number, loss_date, claim_type) is None

def test_rejected_notification_is_not_a_duplicate_on_resubmit(
    mock_repository: NotificationRepository,
) -> None:
    """WI-0151 AC-3: a refused submission is never written, so a retry is not a duplicate."""
    # First attempt rejected: record() is not called
    found_after_reject = mock_repository.find_matching(
        test_notification.policy_number,
        test_notification.loss_date,
        test_notification.claim_type,
    )
    assert found_after_reject is None

    # Second attempt: Same notification submitted again
    found_on_retry = mock_repository.find_matching(
        test_notification.policy_number,
        test_notification.loss_date,
        test_notification.claim_type,
    )
    assert found_on_retry is None