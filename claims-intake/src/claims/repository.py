"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from claims.models import ClaimRecord, NotificationRequest


def _today_utc() -> date:
    """Calendar date of recording, in UTC.

    Section 3 keys the claim reference on the year the notification was recorded.
    A naive `date.today()` would silently follow the machine timezone and can
    issue the wrong year around midnight near 1 January.
    """
    return datetime.now(UTC).date()


class NotificationRepository:
    """Stores recorded notifications and issues claim references.

    There is no path that writes a refused notification. WI-0151 AC-3 holds
    because `record` is the only mutation: a submission the service rejects is
    never passed here, so it can never be the thing a later submission duplicates.
    """

    def __init__(self, clock: Callable[[], date] | None = None) -> None:
        self._records: list[ClaimRecord] = []
        self._next_sequence: int = 1
        self._clock = clock or _today_utc

    def issue_claim_reference(self) -> str:
        """Issue the next `CLM-YYYY-NNNNNN` reference.

        YYYY is the calendar year of issue (section 3). The sequence is unique
        across all records and is never reissued, including references that were
        issued and then not stored.
        """
        year = self._clock().year
        reference = f"CLM-{year:04d}-{self._next_sequence:06d}"
        self._next_sequence += 1
        return reference

    def record(self, notification: NotificationRequest) -> ClaimRecord:
        """Write a notification and return it with its issued claim reference.

        The reference format is fixed by contract section 3. References are unique
        and are never reissued.
        """
        recorded = ClaimRecord(
            claim_reference=self.issue_claim_reference(),
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
    ) -> ClaimRecord | None:
        """Return an existing recorded notification matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. AC-3 is the reason
        this searches recorded notifications only: a submission that was refused
        was never written, so there is nothing for a later one to duplicate.
        Comparison is exact and unnormalised (determination D-1).
        """
        return next(
            (
                recorded
                for recorded in self._records
                if recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ),
            None,
        )
