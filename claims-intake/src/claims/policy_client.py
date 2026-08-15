"""Access to the policy master.

The policy master is a system this service reads from and does not own. Everything
in this module exists to keep one distinction visible: a policy master that answered
and reported no match is a fact about the caller's data, and a policy master that
did not answer is a fact about the system. They reach the caller as different status
codes, so they cannot be the same exception.

`StubPolicyClient` reads `data/policies.json` and stands in for the real dependency
for the whole of Week 1. It can be told to fail, which is how you exercise the
dependency boundary without a dependency.

This module ships complete. You are not asked to write it.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

LookupFailureReason = Literal["timeout", "unreachable", "unparsable"]

DEFAULT_POLICY_DATA = Path(__file__).resolve().parents[2] / "data" / "policies.json"


class PolicyNotFound(Exception):
    """The policy master answered and holds no policy with that number.

    This is a statement about the caller's data. A person should see it.
    """

    def __init__(self, policy_number: str) -> None:
        super().__init__(f"No policy found with number {policy_number!r}")
        self.policy_number = policy_number


class PolicyLookupFailed(Exception):
    """The policy master did not produce a usable answer.

    The caller did nothing wrong and the same request may succeed later. `reason`
    is what lets the HTTP layer choose between the three server-side statuses
    rather than collapsing them into one.
    """

    def __init__(self, policy_number: str, reason: LookupFailureReason) -> None:
        super().__init__(f"Policy lookup failed for {policy_number!r}: {reason}")
        self.policy_number = policy_number
        self.reason: LookupFailureReason = reason


class PolicyRecord:
    """A policy as the master holds it.

    Deliberately a plain object rather than a Pydantic model. Day 2 asks you to
    define the `Policy` model your service works with, and this class is what you
    build it from.
    """

    def __init__(
        self,
        policy_number: str,
        product: str,
        effective_date: date,
        expiry_date: date,
        cancellation_date: date | None,
        limit: Decimal,
        permitted_claim_types: tuple[str, ...],
    ) -> None:
        self.policy_number = policy_number
        self.product = product
        self.effective_date = effective_date
        self.expiry_date = expiry_date
        self.cancellation_date = cancellation_date
        self.limit = limit
        self.permitted_claim_types = permitted_claim_types

    def __repr__(self) -> str:
        return f"PolicyRecord(policy_number={self.policy_number!r})"


class PolicyClient(Protocol):
    """What the service requires of a policy master.

    The service depends on this protocol and not on any particular implementation,
    which is what allows the whole of Week 1 to run against a stub and a later week
    to substitute something that makes a network call without the service changing.
    """

    def get_policy(self, policy_number: str) -> PolicyRecord:
        """Return the policy, or raise.

        Raises:
            PolicyNotFound: the master answered and holds no such policy.
            PolicyLookupFailed: the master did not produce a usable answer.
        """
        ...


class StubPolicyClient:
    """A policy master backed by a JSON file.

    Set `fail_with` to make every lookup raise `PolicyLookupFailed` with that
    reason, which is how a test exercises the three server-side conditions.
    """

    def __init__(
        self,
        data_path: Path | None = None,
        fail_with: LookupFailureReason | None = None,
    ) -> None:
        self._data_path = data_path or DEFAULT_POLICY_DATA
        self.fail_with: LookupFailureReason | None = fail_with
        self._policies: dict[str, PolicyRecord] = {}
        self._load()

    def _load(self) -> None:
        raw = json.loads(self._data_path.read_text())
        for record in raw:
            cancellation = record["cancellation_date"]
            self._policies[record["policy_number"]] = PolicyRecord(
                policy_number=record["policy_number"],
                product=record["product"],
                effective_date=date.fromisoformat(record["effective_date"]),
                expiry_date=date.fromisoformat(record["expiry_date"]),
                cancellation_date=(
                    date.fromisoformat(cancellation) if cancellation else None
                ),
                limit=Decimal(record["limit"]),
                permitted_claim_types=tuple(record["permitted_claim_types"]),
            )

    def get_policy(self, policy_number: str) -> PolicyRecord:
        if self.fail_with is not None:
            raise PolicyLookupFailed(policy_number, self.fail_with)
        try:
            return self._policies[policy_number]
        except KeyError:
            raise PolicyNotFound(policy_number) from None
