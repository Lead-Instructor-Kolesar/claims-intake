# Agent decision log

Day 3. Two decisions the agent drafted during rule implementation. Each is kept or corrected because of a contract rule, a work-item AC, or a specific wrong refusal — not because one shape looked nicer.

## Accepted: V-7 admits only when `loss_date` is strictly before `cancellation_date`

**Produced.** `evaluate_policy_not_cancelled` admits the notification when `cancellation_date` is `null` or when `notification.loss_date < policy.cancellation_date`. A loss on the cancellation date itself fails and returns `POLICY_CANCELLED`.

**Decision.** Accepted as written.

**Reason.** Contract 4.2 V-7 is that condition: `cancellation_date` is null OR `loss_date < cancellation_date`. WI-0158 AC-2: cancellation takes effect at the start of the cancellation date, so a loss on that date is not covered. WI-0158 AC-1: a loss on or after `cancellation_date` is `POLICY_CANCELLED`. Using `<=` the way V-2 and V-3 do would treat equality as still in cover. That notification would then pass V-7, continue the 4.1 walk, and either be recorded or fail V-3 with `LOSS_AFTER_EXPIRY`. Both outcomes are wrong for a loss on the cancellation date: the first records a claim that PR-19 ended, the second sends the handler to the expiry path (WI-0158 AC-4).

## Rejected: V-6 as a member of `POLICY_RULES` / `evaluate_notification` taking a repository

**Produced.** A draft that put `evaluate_not_duplicate` in `POLICY_RULES` and changed `evaluate_notification` to `(notification, policy, repository)` so the tuple could call `find_matching`. That would have compiled, and a test that only checked “duplicates are refused” could still pass.

**Decision.** Rejected. Corrected so `POLICY_RULES` is only V-2, V-7, V-3, V-4, V-5. `evaluate_notification(notification, policy)` does no I/O. `submit_notification` runs V-1, then V-6 via `evaluate_not_duplicate`, then `evaluate_notification`.

**Reason.** Constraint C3: `evaluate_notification` takes a notification and a `Policy` and has no I/O. Duplicate detection is `repository.find_matching` (WI-0151 AC-1: match on recorded `policy_number`, `loss_date`, `claim_type`). Putting that query in `POLICY_RULES` would make `evaluate_notification` a cabinet reader. Contract 4.1 still requires V-6 after V-1 and before V-2: a retry of an already recorded notification is `DUPLICATE_NOTIFICATION` even if the policy would now also fail cover (WI-0151 AC-2: the existing `claim_reference` is what the handler needs). Running V-6 later in the walk would return `POLICY_CANCELLED` or `LOSS_AFTER_EXPIRY` for that retry, and would omit `claim_reference` from `detail`. The 4.1 sequence is preserved in `submit_notification`, not by giving the cover-rule function a repository.

## Gate observation (step 8)

Pushed commit `1530330` with an unused variable. The pull-request job `checks / checks` failed in 11s with exit code 1 (ruff). The Node.js 20 line was a warning only.

Observed: the failing check was marked on the PR. Merge was not blocked. Settings → Branches: "Classic branch protections have not been configured."

That is repository configuration. Required checks are not enforced, so a red job does not disable merge. Reported, not worked around (no branch protection added).

Reverted in `d64f1de`. The following run succeeded (`checks / checks` green in 16s). Merging can be performed automatically on the green head.
