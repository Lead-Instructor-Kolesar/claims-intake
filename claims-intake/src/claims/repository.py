"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import date

from claims.models import RecordedNotification


class NotificationRepository:
    """Stores recorded notifications and issues claim references."""

    def __init__(self) -> None:
        raise NotImplementedError("Day 2 assignment")

    def record(self, notification: object) -> RecordedNotification:
        """Write a notification and return it with its issued claim reference.

        The reference format is fixed by contract section 3. References are unique
        and are never reissued.
        """
        raise NotImplementedError("Day 2 assignment")

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
        raise NotImplementedError("Day 2 assignment")
