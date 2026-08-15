"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. It does not know where notifications are
stored either. It knows the rules.

`evaluate_policy_exists` ships written. It is the pattern every other rule
follows: take the notification and whatever it needs, decide, and return a
`ValidationOutcome` that names the rule and carries the values the decision was
made on. Nothing prints, nothing raises for an ordinary refusal, and nothing
reaches for a status code, because a status code is a fact about HTTP and this
module does not know about HTTP.

Day 3 assignment. Build the remaining rules test-first against
`docs/api-contract.md` section 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from claims.models import NotificationRequest, Policy, RecordedNotification
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of evaluating one rule, or of evaluating them all.

    `passed` is the only thing a caller has to branch on. When it is false, `rule`
    names the rule that decided it, `code` is the stable contract code, and
    `detail` carries the values that produced the decision so that the person
    reading the eventual error can see which input was wrong.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    passed: bool
    rule: str | None = None
    code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls) -> ValidationOutcome:
        return cls(passed=True)

    @classmethod
    def failed(cls, rule: str, code: str, **detail: Any) -> ValidationOutcome:
        return cls(passed=False, rule=rule, code=code, detail=detail)


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> ValidationOutcome:
    """V-1. The policy must exist in the policy master.

    This rule is different from the others in one way that matters: it is the only
    one that reaches outside the service, so it is the only one that can fail for
    a reason that is not the caller's fault. `PolicyNotFound` is caught here and
    turned into an ordinary refusal, because a policy that does not exist is a
    fact about the caller's data. `PolicyLookupFailed` is deliberately not caught,
    because the caller did nothing wrong and the HTTP layer has to be able to tell
    the two apart. Contract section 6 fixes what each becomes.

    V-1 short circuits. Every other rule compares against a field on a policy, and
    if there is no policy there is nothing to compare against. Reporting
    LOSS_BEFORE_INCEPTION for a policy number that does not exist is not merely
    unhelpful, it is a false statement about the client's data (WI-0142, AC-4).
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    return ValidationOutcome.ok()


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    raise NotImplementedError("Day 3 assignment")


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date."""
    raise NotImplementedError("Day 3 assignment")


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    raise NotImplementedError("Day 3 assignment")


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product."""
    raise NotImplementedError("Day 3 assignment")


def evaluate_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Evaluate every rule and return the outcome the caller sees.

    A notification can violate several rules at once and the caller sees one
    reason, so the order this function evaluates in is a caller-visible behavior.
    It is fixed by contract section 4.1 and by nothing else. If you find yourself
    choosing an order here, the contract is incomplete and the fix belongs there.
    """
    raise NotImplementedError("Day 3 assignment")


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> RecordedNotification | ValidationOutcome:
    """Validate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.
    """
    raise NotImplementedError("Day 3 assignment")
