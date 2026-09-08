"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. It does not know where notifications are
stored either. It knows the rules.

`evaluate_notification` is a pure function of a notification and a policy. It
touches nothing outside itself. Lookups and recording belong to
`submit_notification`.
"""

from __future__ import annotations

from collections.abc import Callable

from claims.models import (
    AdmittedNotification,
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RecordedNotification,
    RuleFailure,
    RuleId,
)
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository

PolicyRule = Callable[[NotificationRequest, Policy], RuleFailure | None]


def _failure(rule: str, code: str, **detail: object) -> RuleFailure:
    return RuleFailure(rule=RuleId(rule), code=ErrorCode(code), detail=dict(detail))


def evaluate_not_duplicate(existing: ClaimRecord | None) -> RuleFailure | None:
    """V-6. There must be no recorded notification with the same triple.

    The repository has already answered. This function only decides. A match is
    `DUPLICATE_NOTIFICATION` and carries the existing claim reference (WI-0151
    AC-2). `None` means nothing was recorded, so a prior refusal is not a
    duplicate (WI-0151 AC-3).
    """
    if existing is None:
        return None
    return _failure(
        "V-6",
        "DUPLICATE_NOTIFICATION",
        claim_reference=existing.claim_reference,
    )


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date >= policy.effective_date:
        return None
    return _failure(
        "V-2",
        "LOSS_BEFORE_INCEPTION",
        loss_date=notification.loss_date,
        effective_date=policy.effective_date,
    )


def evaluate_cancellation(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-7. Cover has ended if the loss falls on or after cancellation.

    `cancellation_date` is null when the policy was not cancelled (WI-0158 AC-3).
    The comparison is a strict `<`, so a loss on the cancellation date is not
    covered (WI-0158 AC-2).
    """
    if not policy.is_cancelled:
        return None
    cancellation_date = policy.cancellation_date
    assert cancellation_date is not None
    if notification.loss_date < cancellation_date:
        return None
    return _failure(
        "V-7",
        "POLICY_CANCELLED",
        loss_date=notification.loss_date,
        cancellation_date=cancellation_date,
    )


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-3. The loss must not fall after the policy expiry date."""
    if notification.loss_date <= policy.expiry_date:
        return None
    return _failure(
        "V-3",
        "LOSS_AFTER_EXPIRY",
        loss_date=notification.loss_date,
        expiry_date=policy.expiry_date,
    )


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount <= policy.limit:
        return None
    return _failure(
        "V-4",
        "AMOUNT_EXCEEDS_LIMIT",
        estimated_amount=notification.estimated_amount,
        limit=policy.limit,
    )


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-5. The claim type must be permitted on the policy's product."""
    if notification.claim_type in policy.permitted_claim_types:
        return None
    return _failure(
        "V-5",
        "TYPE_NOT_COVERED",
        claim_type=notification.claim_type,
        permitted_claim_types=policy.permitted_claim_types,
    )


# POLICY_RULES holds only comparisons of a notification to a Policy.
# V-1 reads the policy master and V-6 reads the repository; both are I/O.
# Putting either in this tuple would mix doing into deciding.
# Contract §4.1 order is V-1, then V-6, then this sequence: V-2, V-7, V-3, V-4, V-5.
POLICY_RULES: tuple[PolicyRule, ...] = (
    evaluate_loss_after_inception,
    evaluate_cancellation,
    evaluate_loss_before_expiry,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
)


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate the policy rules. No I/O. First failure wins; None means all passed."""
    for rule in POLICY_RULES:
        failure = rule(notification, policy)
        if failure is not None:
            return failure
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> RecordedNotification | RuleFailure:
    """Resolve the policy, evaluate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.
    """
    try:
        record = policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        # The master answered and said no: that is V-1, a fact about the caller's
        # data. PolicyLookupFailed is not caught. The master did not answer, which
        # is not a rule outcome and must reach the HTTP layer intact.
        return _failure(
            "V-1",
            "POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    policy = Policy.from_record(record)
    duplicate = evaluate_not_duplicate(repository.find_matching(notification))
    if duplicate is not None:
        return duplicate
    failure = evaluate_notification(notification, policy)
    if failure is not None:
        return failure
    recorded = repository.record(AdmittedNotification.admit(notification))
    return recorded.identity
