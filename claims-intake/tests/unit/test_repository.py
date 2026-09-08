"""Tests for `NotificationRepository` against contract section 3 and WI-0151."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from claims.models import NotificationRequest, RecordedNotification
from claims.repository import NotificationRepository

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


def make_notification(**overrides: object) -> NotificationRequest:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    payload.update(overrides)
    return NotificationRequest.model_validate(payload)


def test_recorded_notification_gets_a_contract_claim_reference(
    repository: NotificationRepository,
) -> None:
    notification = make_notification()
    recorded = repository.record(notification)
    assert isinstance(recorded, RecordedNotification)
    assert CLAIM_REFERENCE.fullmatch(recorded.claim_reference)
    assert recorded.claim_reference == f"CLM-{datetime.now(tz=UTC).date().year}-000001"
    assert recorded.policy_number == notification.policy_number
    assert recorded.loss_date == notification.loss_date
    assert recorded.claim_type == notification.claim_type
    assert recorded.estimated_amount == notification.estimated_amount
    assert recorded.description == notification.description


def test_claim_references_are_unique_and_never_reissued(
    repository: NotificationRepository,
) -> None:
    first = repository.record(make_notification()).claim_reference
    second = repository.record(make_notification()).claim_reference
    third = repository.record(make_notification()).claim_reference
    fourth = repository.record(make_notification()).claim_reference
    fifth = repository.record(make_notification()).claim_reference
    references = [first, second, third, fourth, fifth]
    assert len(set(references)) == 5
    assert first.endswith("000001")
    assert second.endswith("000002")
    assert fifth.endswith("000005")
    assert CLAIM_REFERENCE.fullmatch(first)
    assert CLAIM_REFERENCE.fullmatch(second)
    assert CLAIM_REFERENCE.fullmatch(third)
    assert CLAIM_REFERENCE.fullmatch(fourth)
    assert CLAIM_REFERENCE.fullmatch(fifth)


def test_matching_policy_loss_date_and_claim_type_finds_the_recorded_notification(
    repository: NotificationRepository,
) -> None:
    recorded = repository.record(make_notification())
    found = repository.find_matching(
        recorded.policy_number,
        recorded.loss_date,
        recorded.claim_type,
    )
    assert found is recorded
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"claim_type": "theft"}, id="claim_type_differs"),
        pytest.param({"loss_date": "2026-04-03"}, id="loss_date_differs"),
        pytest.param({"policy_number": "MOT-4472"}, id="policy_number_differs"),
    ],
)
def test_notification_agreeing_on_only_two_fields_is_not_a_duplicate(
    repository: NotificationRepository,
    overrides: dict[str, Any],
) -> None:
    recorded = repository.record(make_notification())
    candidate = make_notification(**overrides)
    found = repository.find_matching(
        candidate.policy_number,
        candidate.loss_date,
        candidate.claim_type,
    )
    assert found is None
    still_there = repository.find_matching(
        recorded.policy_number,
        recorded.loss_date,
        recorded.claim_type,
    )
    assert still_there is recorded


def test_wi0151_ac3_rejected_notification_leaves_nothing_to_duplicate(
    repository: NotificationRepository,
) -> None:
    rejected = make_notification(
        policy_number="MOT-4472",
        loss_date="2026-03-18",
        claim_type="theft",
        estimated_amount="12500.00",
    )
    repository.record(make_notification())
    assert (
        repository.find_matching(
            rejected.policy_number,
            rejected.loss_date,
            rejected.claim_type,
        )
        is None
    )


def test_wi0151_ac3_retry_of_unrecorded_submission_is_not_a_duplicate(
    repository: NotificationRepository,
) -> None:
    first_attempt = make_notification()
    assert (
        repository.find_matching(
            first_attempt.policy_number,
            first_attempt.loss_date,
            first_attempt.claim_type,
        )
        is None
    )
    retry = make_notification()
    recorded = repository.record(retry)
    found = repository.find_matching(
        retry.policy_number,
        retry.loss_date,
        retry.claim_type,
    )
    assert found is recorded
