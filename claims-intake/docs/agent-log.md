# Agent decision log

Two decisions made while implementing the rule engine against `docs/api-contract.md` section 4. Each records what changed, what was chosen, what was rejected, and why.

## 1. `evaluate_notification` takes only a notification and a policy

**Change.** The shipped stub of `evaluate_notification` took `(notification, policy_client, repository)`. The implementation takes `(notification, policy)` only.

**Decision.** This function evaluates policy-field rules and returns. It does not look up a policy, does not query recorded notifications, and does not write. V-1 and V-6 stay in `submit_notification`.

**Rejected.** Keep the stub signature and run every rule, including V-1 and V-6, inside `evaluate_notification`. That would look like one function owns the whole table, which would pass a review that only checked that every rule id appeared somewhere.

**Reason.** Contract section 4.1: V-1 is evaluated first and short-circuits; if it fails, no rule that reads a policy field is evaluated (WI-0142 AC-4). A caller that already holds a `Policy` has passed V-1. Giving this function a client would either repeat I/O or skip that short-circuit. Reporting `LOSS_BEFORE_INCEPTION` for a policy number the master does not hold would be a false statement about the caller's data.

## 2. V-6 is applied in `submit_notification`, not in `POLICY_RULES`

**Change.** `POLICY_RULES` is V-2, V-7, V-3, V-5, V-4. The duplicate check runs in `submit_notification` after V-1 and before `evaluate_notification`.

**Decision.** V-6 calls `repository.find_matching` next to `repository.record`. The ordered rule table never receives a repository.

**Rejected.** Put `find_matching` on `POLICY_RULES` so that “every rule is in the table.” Order could still be arranged, but only by threading a repository into `evaluate_notification`, which mixes deciding whether a notification is admissible with writing one.

**Reason.** Contract section 4.1 fixes evaluation order as the table: V-1, then V-6, then the policy-field rows. WI-0151 AC-3: a matching previous submission that was rejected is not a duplicate, because nothing was recorded. The duplicate query therefore belongs with the store that `record` uses. If V-6 lived in `POLICY_RULES`, `evaluate_notification` would have to take a repository, and a later change that recorded before deciding would make a refused notification look like a duplicate on retry.
