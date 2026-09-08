"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, datetime

from claims.models import AdmittedNotification, ClaimRecord, DuplicateKey


class NotificationRepository:
    """Stores recorded notifications and issues claim references."""

    def __init__(self) -> None:
        self._notifications: list[ClaimRecord] = []
        self._sequence = 0

    def record(self, notification: AdmittedNotification) -> ClaimRecord:
        """Write an admitted notification and return it with its claim reference.

        The reference format is fixed by contract section 3. References are unique
        and are never reissued. A NotificationRequest cannot be passed here: only
        a FNOL that has already been admitted is stored, so a refused submission
        can never become a later duplicate (WI-0151 AC-3).
        """
        self._sequence += 1
        recorded = ClaimRecord.issue(
            notification,
            f"CLM-{datetime.now(tz=UTC).year}-{self._sequence:06d}",
        )
        self._notifications.append(recorded)
        return recorded

    def find_matching(self, candidate: DuplicateKey) -> ClaimRecord | None:
        """Return an existing recorded notification matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. Equality is exact
        and case-sensitive (EDGE-07 / contract §2.2 and V-1). AC-3 is the reason
        this searches recorded notifications only: a submission that was refused
        was never written, so there is nothing for a later one to duplicate.
        """
        for recorded in self._notifications:
            if recorded.matches(candidate):
                return recorded
        return None
