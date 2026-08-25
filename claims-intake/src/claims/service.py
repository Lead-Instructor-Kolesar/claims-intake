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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claims.models import (
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of evaluating one rule, or of evaluating them all.

    `passed` is the only thing a caller has to branch on. When it is false,
    `failure` is the `RuleFailure` that decided it, and `detail` carries the values
    that produced the decision so that the person reading the eventual error can
    see which input was wrong.

    A refusal is carried as a `RuleFailure` rather than as two loose strings, so
    the rule label and the contract code cannot be transposed on the one path that
    actually produces refusals. `rule` and `code` remain readable directly because
    that is the vocabulary the contract uses, but they are derived, not stored.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    passed: bool
    failure: RuleFailure | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def rule(self) -> RuleId | None:
        """The rule that refused, or None when nothing refused."""
        return None if self.failure is None else self.failure.rule

    @property
    def code(self) -> ErrorCode | None:
        """The section 6 code for the refusal, or None when nothing refused."""
        return None if self.failure is None else self.failure.code

    @classmethod
    def ok(cls) -> ValidationOutcome:
        return cls(passed=True)

    @classmethod
    def failed(cls, rule: RuleId, code: ErrorCode, **detail: Any) -> ValidationOutcome:
        return cls(passed=False, failure=RuleFailure(rule=rule, code=code), detail=detail)


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


def evaluate_policy_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-7. Cover must not have been ended by a cancellation before the loss.

    The comparison is strict: `loss_date` earlier than `cancellation_date` passes,
    equal fails, later fails. Cancellation takes effect at the start of the
    cancellation date, so the last covered day is the day before (WI-0158, AC-2).

    A `None` cancellation date is the only representation of "not cancelled" and
    this rule does not apply to it (WI-0158, AC-3). The narrowing below is what
    the type demands, which is why the absence case cannot be forgotten.

    This rule reads `cancellation_date` and never `expiry_date`. A cancelled
    policy is refused here whether the loss falls inside the original term or
    outside it, and because this is stage 2 the caller is told the policy was
    cancelled rather than that the loss was late (WI-0158, AC-4).
    """
    cancellation_date = policy.cancellation_date
    if cancellation_date is None or notification.loss_date < cancellation_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-7",
        code="POLICY_CANCELLED",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        cancellation_date=cancellation_date,
    )


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date >= policy.effective_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-2",
        code="LOSS_BEFORE_INCEPTION",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        effective_date=policy.effective_date,
    )


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date."""
    if notification.loss_date <= policy.expiry_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-3",
        code="LOSS_AFTER_EXPIRY",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        expiry_date=policy.expiry_date,
    )


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount <= policy.limit:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-4",
        code="AMOUNT_EXCEEDS_LIMIT",
        policy_number=notification.policy_number,
        estimated_amount=notification.estimated_amount,
        limit=policy.limit,
    )


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product.

    The claim type is already known to be one of the five values in section 2.3,
    because a value outside the vocabulary never leaves stage 0 (determination
    D-2). This rule asks the narrower question the contract reserves for it:
    whether the product this policy is written on extends to that peril.
    """
    if notification.claim_type in policy.permitted_claim_types:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-5",
        code="TYPE_NOT_COVERED",
        policy_number=notification.policy_number,
        claim_type=notification.claim_type,
        permitted_claim_types=policy.permitted_claim_types,
        product=policy.product,
    )


def evaluate_not_duplicate(
    notification: NotificationRequest,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-6. The loss must not already have been recorded.

    The match is the three-field composite WI-0151 AC-1 fixes, and the repository
    owns it. `estimated_amount` and `description` are not part of the key, so a
    resubmission differing only in amount is still a duplicate.

    The refusal carries the `claim_reference` of the record that already exists
    (WI-0151, AC-2). It is not a reference for the submission being refused;
    nothing is recorded here.
    """
    existing = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if existing is None:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-6",
        code="DUPLICATE_NOTIFICATION",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        claim_type=notification.claim_type,
        claim_reference=existing.claim_reference,
    )


PolicyRule = Callable[[NotificationRequest, Policy], ValidationOutcome]

# Contract section 4.1. Each tuple is one stage, in the order the stages run, and
# the rules inside a stage are in ascending identifier order. This table is the
# only statement of evaluation order in the code: V-7 sits in stage 2 ahead of
# V-3 in stage 3, which is what WI-0158 AC-4 requires. Stage 1 (V-1) is not here
# because it reads the master rather than a policy field, and stage 5 (V-6) is
# not here because it reads the repository.
_POLICY_RULE_STAGES: tuple[tuple[PolicyRule, ...], ...] = (
    (evaluate_policy_not_cancelled,),
    (evaluate_loss_after_inception, evaluate_loss_before_expiry),
    (evaluate_amount_within_limit, evaluate_claim_type_covered),
)


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
    policy_exists = evaluate_policy_exists(notification, policy_client)
    if not policy_exists.passed:
        return policy_exists

    # V-1 owns the existence decision, so it is not inlined here. This second read
    # is what supplies the fields stages 2 through 4 compare against, and it cannot
    # raise PolicyNotFound now that V-1 has passed. A client that makes a network
    # call should cache the lookup; that is the client's concern, not the rules'.
    policy = Policy.from_record(policy_client.get_policy(notification.policy_number))

    for stage in _POLICY_RULE_STAGES:
        for rule in stage:
            outcome = rule(notification, policy)
            if not outcome.passed:
                return outcome

    return evaluate_not_duplicate(notification, repository)


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ClaimRecord | ValidationOutcome:
    """Validate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.
    """
    outcome = evaluate_notification(notification, policy_client, repository)
    if not outcome.passed:
        return outcome
    return repository.record(notification)
