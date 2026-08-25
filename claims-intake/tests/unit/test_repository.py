"""Unit tests for recorded-notification persistence.

Recording, reference issue, and duplicate matching are tested as separate
behaviours. Fixtures return a fresh repository; helpers return a fresh request.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimType, NotificationRequest
from claims.policy_client import StubPolicyClient
from claims.repository import NotificationRepository

_CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


def notification_request(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: Decimal = Decimal("4200.00"),
    description: str | None = "Rear ended at a junction.",
) -> NotificationRequest:
    """A well-formed request. Each call returns a new instance."""
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
        description=description,
    )


def test_record_returns_claim_reference_matching_section_3_format(
    repository: NotificationRepository,
    policy_client: StubPolicyClient,
) -> None:
    policy = policy_client.get_policy("MOT-4471")
    recorded = repository.record(notification_request(policy_number=policy.policy_number))
    assert _CLAIM_REFERENCE.fullmatch(recorded.claim_reference)
    assert recorded.policy_number == policy.policy_number
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.claim_type == "collision"
    assert recorded.estimated_amount == Decimal("4200.00")


def test_issue_claim_reference_matches_section_3_format(
    repository: NotificationRepository,
) -> None:
    assert _CLAIM_REFERENCE.fullmatch(repository.issue_claim_reference())


def test_claim_reference_uses_calendar_year_of_recording() -> None:
    repository = NotificationRepository(clock=lambda: date(2026, 8, 25))
    recorded = repository.record(notification_request())
    assert recorded.claim_reference == "CLM-2026-000001"


def test_claim_reference_year_follows_the_clock_on_issue() -> None:
    repository = NotificationRepository(clock=lambda: date(2027, 1, 1))
    assert repository.issue_claim_reference() == "CLM-2027-000001"


def test_no_two_records_share_a_claim_reference(
    repository: NotificationRepository,
    policy_client: StubPolicyClient,
) -> None:
    first_policy = policy_client.get_policy("MOT-4471")
    second_policy = policy_client.get_policy("MOT-4472")
    third_policy = policy_client.get_policy("MOT-4473")
    first = repository.record(notification_request(policy_number=first_policy.policy_number))
    second = repository.record(
        notification_request(
            policy_number=second_policy.policy_number,
            loss_date=date(2026, 3, 18),
            claim_type="theft",
        )
    )
    third = repository.record(
        notification_request(
            policy_number=third_policy.policy_number,
            loss_date=date(2026, 2, 27),
            claim_type="glass",
        )
    )
    references = {first.claim_reference, second.claim_reference, third.claim_reference}
    assert len(references) == 3


def test_issued_claim_references_are_never_reissued(repository: NotificationRepository) -> None:
    first = repository.issue_claim_reference()
    second = repository.issue_claim_reference()
    assert first != second
    assert _CLAIM_REFERENCE.fullmatch(first)
    assert _CLAIM_REFERENCE.fullmatch(second)


def test_find_matching_returns_record_when_all_three_fields_agree(
    repository: NotificationRepository,
) -> None:
    recorded = repository.record(notification_request())
    found = repository.find_matching("MOT-4471", date(2026, 4, 2), "collision")
    assert found is recorded
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param(
            "MOT-4472",
            date(2026, 4, 2),
            "collision",
            id="only_policy_number_differs",
        ),
        pytest.param(
            "MOT-4471",
            date(2026, 5, 1),
            "collision",
            id="only_loss_date_differs",
        ),
        pytest.param(
            "MOT-4471",
            date(2026, 4, 2),
            "theft",
            id="only_claim_type_differs",
        ),
    ],
)
def test_notification_agreeing_on_only_two_fields_is_not_a_duplicate(
    repository: NotificationRepository,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    repository.record(notification_request())
    assert repository.find_matching(policy_number, loss_date, claim_type) is None


def test_duplicate_key_does_not_include_estimated_amount_or_description(
    repository: NotificationRepository,
) -> None:
    """WI-0151 AC-1: amount and description are not part of the match."""
    recorded = repository.record(
        notification_request(
            estimated_amount=Decimal("100.00"),
            description="first submission",
        )
    )
    found = repository.find_matching("MOT-4471", date(2026, 4, 2), "collision")
    assert found is recorded
    resubmission = notification_request(
        estimated_amount=Decimal("9999.00"),
        description="retry after timeout",
    )
    assert (
        repository.find_matching(
            resubmission.policy_number,
            resubmission.loss_date,
            resubmission.claim_type,
        )
        is recorded
    )


def test_rejected_notification_leaves_nothing_to_duplicate(
    repository: NotificationRepository,
) -> None:
    """WI-0151 AC-3: a refused submission is never written.

    The repository has no reject path. A notification that fails a rule is simply
    not recorded, so a later submission of the same key is an original.
    """
    refused = notification_request()
    assert (
        repository.find_matching(
            refused.policy_number,
            refused.loss_date,
            refused.claim_type,
        )
        is None
    )
    recorded = repository.record(refused)
    assert (
        repository.find_matching(
            refused.policy_number,
            refused.loss_date,
            refused.claim_type,
        )
        is recorded
    )


def test_policy_number_match_is_exact_and_case_sensitive(
    repository: NotificationRepository,
) -> None:
    """Determination D-1: mot-4471 is not MOT-4471."""
    repository.record(notification_request(policy_number="MOT-4471"))
    assert repository.find_matching("mot-4471", date(2026, 4, 2), "collision") is None
