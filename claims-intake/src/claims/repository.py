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

# PERSISTENCE = LIST OF TYPE RecordedNotification

class NotificationRepository:
    """Stores recorded notifications and issues claim references."""

    def __init__(self) -> None:
        self._records: list[RecordedNotification] = []
        self._sequence: int = 0

    def issue_claim_reference(self, recorded_on: date) -> str:
        """Return the next `CLM-YYYY-NNNNNN`. Never reissued, even if unused."""
        self._sequence += 1
        return f"CLM-{recorded_on.year:04d}-{self._sequence:06d}"

    def record(
        self,
        notification: NotificationRequest,
        recorded_on: date | None = None,
    ) -> RecordedNotification:
        """Write a notification and return it with its issued claim reference.

        Always writes. Does not call `find_matching` and refuse: deciding
        duplicates is Day 3. WI-0151 AC-3 is why there is no reject-write path —
        a refused notification was never recorded, so it cannot be duplicated.
        """
        if recorded_on is None:
            recorded_on = datetime.now(tz=UTC).date()
        recorded = RecordedNotification(
            claim_reference=self.issue_claim_reference(recorded_on),
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
        self._records.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> RecordedNotification | None:
        """Return an existing recorded notification matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. AC-3 is the reason
        this searches recorded notifications only: a submission that was refused
        was never written, so there is nothing for a later one to duplicate.
        """
        for record in self._records:
            if (
                record.policy_number == policy_number
                and record.loss_date == loss_date
                and record.claim_type == claim_type
            ):
                return record
        return None
