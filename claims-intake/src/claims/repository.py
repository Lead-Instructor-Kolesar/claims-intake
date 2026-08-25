"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import NotificationRequest, RecordedNotification


class NotificationRepository:
    """Stores recorded notifications and issues claim references."""

    def __init__(self) -> None:
        self._notifications: list[RecordedNotification] = []
        self._sequence = 0

    def record(self, notification: NotificationRequest) -> RecordedNotification:
        """Write a notification and return it with its issued claim reference.

        The reference format is fixed by contract section 3. References are unique
        and are never reissued.
        """
        self._sequence += 1
        recorded = RecordedNotification(
            claim_reference=f"CLM-{datetime.now(tz=UTC).year}-{self._sequence:06d}",
            status="recorded",
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
        self._notifications.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> RecordedNotification | None:
        """Return an existing recorded notification matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. Equality is exact
        and case-sensitive (EDGE-07 / contract §2.2 and V-1). AC-3 is the reason
        this searches recorded notifications only: a submission that was refused
        was never written, so there is nothing for a later one to duplicate.
        """
        for recorded in self._notifications:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None
