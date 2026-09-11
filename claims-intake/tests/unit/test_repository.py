"""Pin recording and WI-0151 duplicate lookup. Fixtures are fresh per test."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimType, NotificationRequest, RecordedNotification
from claims.repository import NotificationRepository, format_claim_reference


def _record(
    repository: NotificationRepository, notification: NotificationRequest
) -> RecordedNotification:
    return repository.record(
        RecordedNotification.from_accepted(
            notification, repository.allocate_claim_reference()
        )
    )


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recorded_on=date(2026, 8, 25))


@pytest.fixture
def accepted_notification() -> NotificationRequest:
    return NotificationRequest(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )


@pytest.mark.parametrize(
    ("year", "sequence", "expected"),
    [
        pytest.param(2026, 1, "CLM-2026-000001", id="first-reference"),
        pytest.param(2026, 317, "CLM-2026-000317", id="section-3-example"),
        pytest.param(2027, 42, "CLM-2027-000042", id="year-of-recording-not-loss-date"),
    ],
)
def test_format_claim_reference_matches_section_3(
    year: int, sequence: int, expected: str
) -> None:
    assert format_claim_reference(year, sequence) == expected


@pytest.mark.parametrize(
    ("policy_number", "expected_reference"),
    [
        pytest.param("MOT-4471", "CLM-2026-000001", id="first-record-CLM-2026-000001"),
        pytest.param("MOT-4472", "CLM-2026-000001", id="first-record-independent-of-policy"),
    ],
)
def test_record_issues_a_section_3_claim_reference(
    repository: NotificationRepository,
    policy_number: str,
    expected_reference: str,
) -> None:
    notification = NotificationRequest(
        policy_number=policy_number,
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
    )
    recorded = _record(repository, notification)
    assert recorded.claim_reference == expected_reference


@pytest.mark.parametrize(
    ("second_policy", "expected_second_reference"),
    [
        pytest.param("MOT-4472", "CLM-2026-000002", id="second-record-CLM-2026-000002"),
        pytest.param("MOT-4473", "CLM-2026-000002", id="sequence-not-tied-to-policy-number"),
    ],
)
def test_claim_references_are_unique(
    repository: NotificationRepository,
    second_policy: str,
    expected_second_reference: str,
) -> None:
    first = _record(
        repository,
        NotificationRequest(
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
        ),
    )
    second = _record(
        repository,
        NotificationRequest(
            policy_number=second_policy,
            loss_date=date(2026, 4, 3),
            claim_type="theft",
            estimated_amount=Decimal("12500.00"),
        ),
    )
    assert first.claim_reference != second.claim_reference
    assert second.claim_reference == expected_second_reference


@pytest.mark.parametrize(
    "expected_reference",
    [
        pytest.param("CLM-2026-000001", id="allocate-does-not-persist"),
    ],
)
def test_allocate_claim_reference_does_not_write(
    repository: NotificationRepository,
    accepted_notification: NotificationRequest,
    expected_reference: str,
) -> None:
    allocated = repository.allocate_claim_reference()
    assert allocated == expected_reference
    assert (
        repository.find_matching(
            accepted_notification.policy_number,
            accepted_notification.loss_date,
            accepted_notification.claim_type,
        )
        is None
    )


@pytest.mark.parametrize(
    "description",
    [
        pytest.param("Rear ended at a junction.", id="description-present"),
        pytest.param(None, id="description-null"),
    ],
)
def test_record_copies_notification_fields(
    repository: NotificationRepository,
    description: str | None,
) -> None:
    notification = NotificationRequest(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description=description,
    )
    recorded = _record(repository, notification)
    assert recorded.policy_number == notification.policy_number
    assert recorded.loss_date == notification.loss_date
    assert recorded.claim_type == notification.claim_type
    assert recorded.estimated_amount == notification.estimated_amount
    assert recorded.description == notification.description


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param(
            "MOT-4471",
            date(2026, 4, 2),
            "theft",
            id="same-policy-date-different-claim_type",
        ),
        pytest.param(
            "MOT-4471",
            date(2026, 4, 3),
            "collision",
            id="same-policy-claim_type-different-loss_date",
        ),
        pytest.param(
            "MOT-4472",
            date(2026, 4, 2),
            "collision",
            id="same-date-claim_type-different-policy_number",
        ),
    ],
)
def test_find_matching_requires_all_three_fields(
    repository: NotificationRepository,
    accepted_notification: NotificationRequest,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    _record(repository, accepted_notification)
    assert repository.find_matching(policy_number, loss_date, claim_type) is None


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param(
            "MOT-4471",
            date(2026, 4, 2),
            "collision",
            id="WI-0151-AC-1-all-three-match",
        ),
    ],
)
def test_find_matching_returns_the_recorded_notification(
    repository: NotificationRepository,
    accepted_notification: NotificationRequest,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    recorded = _record(repository, accepted_notification)
    found = repository.find_matching(policy_number, loss_date, claim_type)
    assert found is recorded
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    "policy_number",
    [
        pytest.param("MOT-4471", id="WI-0151-AC-3-never-recorded"),
    ],
)
def test_unrecorded_submission_is_not_a_duplicate(
    repository: NotificationRepository,
    policy_number: str,
) -> None:
    notification = NotificationRequest(
        policy_number=policy_number,
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
    )
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )
    recorded = _record(repository, notification)
    found = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    assert found is recorded
