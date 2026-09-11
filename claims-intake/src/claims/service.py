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
from typing import Any, cast

from claims.models import (
    ClaimType,
    ErrorCode,
    NotificationRequest,
    Policy,
    RecordedNotification,
    RuleFailure,
    RuleIdentifier,
)
from claims.policy_client import PolicyClient, PolicyNotFound, PolicyRecord
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
    claim_reference: str | None = None
    failure: RuleFailure | None = None

    @classmethod
    def ok(cls, claim_reference: str | None = None) -> ValidationOutcome:
        return cls(passed=True, claim_reference=claim_reference)

    @classmethod
    def failed(cls, rule: str, code: str, **detail: Any) -> ValidationOutcome:
        return cls(
            passed=False,
            rule=rule,
            code=code,
            detail=detail,
            failure=RuleFailure(
                rule=cast(RuleIdentifier, rule),
                code=cast(ErrorCode, code),
            ),
        )


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

    Outcome: admit when loss_date >= effective_date, else LOSS_BEFORE_INCEPTION.
    Authority: contract 4.2 V-2; WI-0142 AC-3 (equality is covered).
    Boundary: inclusive on the inception date.
    """
    if notification.loss_date >= policy.effective_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-2",
        "LOSS_BEFORE_INCEPTION",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date.isoformat(),
        effective_date=policy.effective_date.isoformat(),
    )


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date.

    Outcome: admit when loss_date <= expiry_date, else LOSS_AFTER_EXPIRY.
    Authority: contract 4.2 V-3 (inclusive on expiry).
    Boundary: a loss on expiry_date is covered.
    """
    if notification.loss_date <= policy.expiry_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-3",
        "LOSS_AFTER_EXPIRY",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date.isoformat(),
        expiry_date=policy.expiry_date.isoformat(),
    )


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    Outcome: admit when estimated_amount <= limit, else AMOUNT_EXCEEDS_LIMIT.
    Authority: contract 4.2 V-4.
    Boundary: an amount equal to limit is within cover.
    """
    if notification.estimated_amount <= policy.limit:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-4",
        "AMOUNT_EXCEEDS_LIMIT",
        policy_number=notification.policy_number,
        estimated_amount=str(notification.estimated_amount),
        limit=str(policy.limit),
    )


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product.

    Outcome: admit when claim_type is in permitted_claim_types, else
    TYPE_NOT_COVERED.
    Authority: contract 4.2 V-5. Non-vocabulary values never reach this rule
    (W-2).
    Boundary: membership, exact and case-sensitive.
    """
    if notification.claim_type in policy.permitted_claim_types:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-5",
        "TYPE_NOT_COVERED",
        policy_number=notification.policy_number,
        claim_type=notification.claim_type,
        product=policy.product,
        permitted_claim_types=list(policy.permitted_claim_types),
    )


def evaluate_policy_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-7. Cover has ended if the policy was cancelled on or before the loss date.

    Outcome: admit when cancellation_date is null OR loss_date < cancellation_date,
    else POLICY_CANCELLED.
    Authority: contract 4.2 V-7; WI-0158 AC-1, AC-2, AC-3.
    Boundary: strict less-than. A loss on the cancellation date is not covered.
    """
    if policy.cancellation_date is None or notification.loss_date < policy.cancellation_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-7",
        "POLICY_CANCELLED",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date.isoformat(),
        cancellation_date=policy.cancellation_date.isoformat(),
    )


def evaluate_not_duplicate(
    notification: NotificationRequest,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-6. The three-field composite must not already be recorded (WI-0151).

    Outcome: admit when find_matching returns None, else DUPLICATE_NOTIFICATION
    with the existing claim_reference (WI-0151 AC-2).
    Authority: contract 4.2 V-6; WI-0151 AC-1, AC-3.
    Boundary: all three of policy_number, loss_date, claim_type. A refused
    submission was never recorded, so it is not an N.

    This is a query against the cabinet, not a function of a Policy, so it is
    not a member of POLICY_RULES. submit_notification calls it after V-1 and
    before evaluate_notification so contract 4.1 still holds: V-1, V-6, V-2,
    V-7, V-3, V-4, V-5.
    """
    existing = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if existing is None:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        "V-6",
        "DUPLICATE_NOTIFICATION",
        policy_number=notification.policy_number,
        loss_date=notification.loss_date.isoformat(),
        claim_type=notification.claim_type,
        claim_reference=existing.claim_reference,
    )


# POLICY_RULES is only rules that are functions of (notification, policy).
# V-6 needs repository.find_matching (WI-0151). Putting that lookup in this
# tuple would force evaluate_notification to take a repository, which C3
# forbids: evaluate_notification(notification, policy) has no I/O.
# Contract 4.1 still runs V-6 after V-1 and before V-2; that call is in
# submit_notification, not here. Order in this tuple is 4.1 among Policy
# rules: V-2, V-7, V-3, V-4, V-5.
POLICY_RULES = (
    evaluate_loss_after_inception,
    evaluate_policy_not_cancelled,
    evaluate_loss_before_expiry,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
)


def _policy_from_record(record: PolicyRecord) -> Policy:
    return Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=cast(tuple[ClaimType, ...], record.permitted_claim_types),
    )


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate the cover-period and product rules. No I/O.

    Walks POLICY_RULES only. V-1 is evaluate_policy_exists (needs the client).
    V-6 is evaluate_not_duplicate (needs the repository). Both run in
    submit_notification so the 4.1 sequence is preserved without giving this
    function a repository.
    """
    for rule in POLICY_RULES:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return RuleFailure(
                rule=cast(RuleIdentifier, outcome.rule),
                code=cast(ErrorCode, outcome.code),
            )
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Validate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.

    Evaluation order (contract 4.1) is applied here, not inside POLICY_RULES:
    V-1 via the policy client, then V-6 via the repository, then
    evaluate_notification for V-2, V-7, V-3, V-4, V-5. V-6 is not in
    POLICY_RULES because duplicate detection is a query against recorded
    notifications (WI-0151), not a comparison against a Policy.

    The only exception caught is PolicyNotFound (the master answered: V-1).
    PolicyLookupFailed is not a rule outcome and is not caught, so its reason
    reaches the HTTP layer intact (contract section 6).
    """
    try:
        record = policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            "V-1",
            "POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )

    duplicate = evaluate_not_duplicate(notification, repository)
    if not duplicate.passed:
        return duplicate

    # Walk POLICY_RULES here so the HTTP layer receives section 5.1 detail.
    # evaluate_notification returns RuleFailure only (C3); that type has no detail.
    policy = _policy_from_record(record)
    for rule in POLICY_RULES:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return outcome

    recorded = repository.record(
        RecordedNotification.from_accepted(
            notification, repository.allocate_claim_reference()
        )
    )
    return ValidationOutcome.ok(claim_reference=recorded.claim_reference)
