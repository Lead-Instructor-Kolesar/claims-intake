"""Persistence for recorded notifications (contract section 3, WI-0151).

`record` writes a RecordedNotification. `find_matching` queries the
three-field composite. The cabinet does not accept NotificationRequest: a
rejected submission cannot be stored through this interface.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import ClaimType, RecordedNotification


def format_claim_reference(year: int, sequence: int) -> str:
    return f"CLM-{year:04d}-{sequence:06d}"


class NotificationRepository:
    def __init__(self, recorded_on: date | None = None) -> None:
        # Section 3: YYYY is the year of recording. Tests pin it; default is UTC today.
        self._recorded_on = recorded_on or datetime.now(tz=UTC).date()
        self._records: list[RecordedNotification] = []
        self._next_sequence = 1

    def allocate_claim_reference(self) -> str:
        reference = format_claim_reference(self._recorded_on.year, self._next_sequence)
        self._next_sequence += 1
        return reference

    def record(self, notification: RecordedNotification) -> RecordedNotification:
        # Does not decide duplicates. V-6 calls find_matching first (WI-0151).
        self._records.append(notification)
        return notification

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: ClaimType,
    ) -> RecordedNotification | None:
        for recorded in self._records:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None
