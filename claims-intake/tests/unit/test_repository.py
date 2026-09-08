"""Store-boundary tests for NotificationRepository.

Recording, reference generation, and duplicate querying are tested as separate
behaviours so none of them has to be reached through another. The repository
does not decide duplicates (Day 3); `find_matching` only reports whether a
recorded notification exists. WI-0151 AC-3 is demonstrated by never calling
`record`, then observing that `find_matching` returns None.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import get_type_hints

import pytest

from claims.models import NotificationRequest, RecordedNotification
from claims.repository import NotificationRepository


def test_record_returns_claim_reference_matching_contract_format(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    # YYYY is the year of recording, not the loss year (contract §3).
    recorded = repository.record(
        make_notification(loss_date=date(2025, 12, 1)),
        recorded_on=date(2026, 8, 25),
    )
    assert recorded.claim_reference == "CLM-2026-000001"


def test_no_two_records_share_a_claim_reference(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    recorded_on = date(2026, 1, 15)
    first = repository.record(make_notification(policy_number="MOT-0001"), recorded_on=recorded_on)
    second = repository.record(make_notification(policy_number="MOT-0002"), recorded_on=recorded_on)
    third = repository.record(make_notification(policy_number="MOT-0003"), recorded_on=recorded_on)
    assert first.claim_reference == "CLM-2026-000001"
    assert second.claim_reference == "CLM-2026-000002"
    assert third.claim_reference == "CLM-2026-000003"
    assert len({first.claim_reference, second.claim_reference, third.claim_reference}) == 3


def test_issue_claim_reference_never_reissues_unused_values(
    repository: NotificationRepository,
) -> None:
    recorded_on = date(2026, 4, 2)
    first = repository.issue_claim_reference(recorded_on)
    second = repository.issue_claim_reference(recorded_on)
    assert first == "CLM-2026-000001"
    assert second == "CLM-2026-000002"
    assert first != second


def test_find_matching_returns_recorded_notification_when_all_three_fields_agree(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    notification = make_notification()
    recorded = repository.record(notification, recorded_on=date(2026, 4, 2))
    found = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    assert found is not None
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_number", "MOT-4472"),
        ("loss_date", date(2026, 4, 3)),
        ("claim_type", "theft"),
    ],
    ids=["differing_policy_number", "differing_loss_date", "differing_claim_type"],
)
def test_find_matching_returns_none_when_only_two_of_three_fields_agree(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
    field: str,
    value: str | date,
) -> None:
    # WI-0151 AC-1: the composite is all three fields. Two of three is not a duplicate.
    original = make_notification()
    repository.record(original, recorded_on=date(2026, 4, 2))
    differing = make_notification(**{field: value})
    found = repository.find_matching(
        differing.policy_number,
        differing.loss_date,
        differing.claim_type,
    )
    assert found is None


def test_unrecorded_notification_is_not_a_duplicate(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    """WI-0151 AC-3: a refused submission is never written, so it cannot be duplicated.

    The repository has no reject-write path. Not calling `record` is the refused
    submission; `find_matching` then returns None. After a later `record`, the
    same three fields are stored.
    """
    notification = make_notification()
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )
    recorded = repository.record(notification, recorded_on=date(2026, 4, 2))
    found = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    assert found is not None
    assert found.claim_reference == recorded.claim_reference


def test_record_does_not_refuse_a_second_write_with_the_same_three_fields(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    # Deciding duplicates is Day 3. If this refused, V-6 would live in the store.
    first = repository.record(make_notification(), recorded_on=date(2026, 4, 2))
    second = repository.record(make_notification(), recorded_on=date(2026, 4, 2))
    assert first.claim_reference != second.claim_reference


def test_record_accepts_notification_request_not_a_raw_dictionary() -> None:
    hints = get_type_hints(NotificationRepository.record)
    assert hints["notification"] is NotificationRequest
    assert hints["return"] is RecordedNotification


def test_find_matching_does_not_use_amount_or_description(
    repository: NotificationRepository,
    make_notification: Callable[..., NotificationRequest],
) -> None:
    # WI-0151 AC-1 names three fields. Amount and description do not participate.
    original = make_notification(
        estimated_amount=Decimal("100.00"),
        description="first wording",
    )
    recorded = repository.record(original, recorded_on=date(2026, 4, 2))
    found = repository.find_matching(
        original.policy_number,
        original.loss_date,
        original.claim_type,
    )
    assert found is not None
    assert found.claim_reference == recorded.claim_reference
    assert found.estimated_amount == Decimal("100.00")
