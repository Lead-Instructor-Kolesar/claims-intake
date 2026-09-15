# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification


| Payload | Outcome  | Rule | Code                  | Status |
| ------- | -------- | ---- | --------------------- | ------ |
| EDGE-01 | Accepted | -    | -                     | -      |
| EDGE-02 | Accepted | -    | -                     | -      |
| EDGE-03 | Accepted | -    | -                     | -      |
| EDGE-04 | Rejected | V-7  | POLICY_CANCELLED      | 422    |
| EDGE-05 | Rejected | V-2  | LOSS_BEFORE_INCEPTION | 422    |
| EDGE-06 | Rejected | V-4  | AMOUNT_EXCEEDS_LIMIT  | 422    |
| EDGE-07 | Rejected | V-1  | POLICY_NOT_FOUND      | 422    |
| EDGE-08 | Rejected | -    | MALFORMED_REQUEST     | 400    |
| EDGE-09 | Rejected | V-5  | TYPE_NOT_COVERED      | 422    |
| EDGE-10 | Rejected | V-7  | POLICY_CANCELLED      | 422    |
| EDGE-11 | Rejected | -    | MALFORMED_REQUEST     | 400    |
| EDGE-12 | Rejected | -    | MALFORMED_REQUEST     | 400    |


## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07

**The ambiguity.** What the contract failed to determine, and the two readings that were both available.

Section 2.2 called `policy_number` the identifier “as held in the policy master” but did not say whether the lookup is case-sensitive. `mot-4471` either matches `MOT-4471` and the notification is accepted, or it does not and V-1 returns `POLICY_NOT_FOUND`.

**Decision.** What the service does.

The lookup is exact, including case. `mot-4471` is not in the policy master. The service rejects with `POLICY_NOT_FOUND` (422). V-1 short-circuits, so no rule that reads a policy field is evaluated.

**Authority.** The work item, acceptance criterion, or product rule that supports it.

Section 2.2: the identifier as held in the policy master. WI-0142 AC-4: a policy number that is not found is `POLICY_NOT_FOUND` and is not evaluated against later rules.

**Rejected alternative.** The other reading, and why it is wrong rather than merely less preferred.

Treating the lookup as case-insensitive would record a notification against a key the caller did not send. The portal keyed a different string. That is the caller’s data, not an identifier held in the master.

**Contract amended.** Section and what changed.

Section 2.2: `policy_number` is matched exactly, including case. Section 4.1: V-1 is evaluated first and short-circuits (WI-0142 AC-4). Section 4.2: V-1 is the first row of the table.

### Decision 2

**Payload.** EDGE-11

**The ambiguity.**

`flood` is not in the section 2.3 vocabulary. One reading: the body cannot be interpreted, status `400` (section 2.4 — the caller’s code sent a value this contract does not define for `claim_type`). The other: the body is well formed and V-5 refuses it with `TYPE_NOT_COVERED` (422), because `flood` is also not on MOT-4471’s product.

**Decision.**

`flood` is not well formed. Status `400`. No section 4 rule runs. Rule, code, and the V-5 path do not apply.

**Authority.**

Section 2.2: `claim_type` is “one of the values in 2.3.” Section 2.4: a request that cannot be interpreted is `400`; the caller’s code is wrong. V-5 compares a vocabulary value to the product’s permitted subset; it does not define the vocabulary.

**Rejected alternative.**

Returning `TYPE_NOT_COVERED` is wrong because that code means “this vocabulary value is not permitted on this product” (EDGE-09: `collision` on named perils). `flood` is not a vocabulary value. Using V-5 would also require a policy lookup for a payload the service cannot interpret.

**Contract amended.**

Section 2.3: a `claim_type` outside the list is `400` under 2.4. Section 2.4: that case is listed with the other well-formedness refusals.

### Decision 3

**Payload.** EDGE-12

**The ambiguity.**

`estimated_amount` is `"3499.999"` (three decimal places). Section 2.2 required two decimal places but did not say whether extra scale is a shape error (`400`) or a decimal the service still interprets. If interpreted, V-4 passes against MOT-4476’s limit of `75000.00` and the notification would be accepted.

**Decision.**

A value that is not exactly two decimal places cannot be interpreted. Status `400`. Nothing is recorded.

**Authority.**

Section 2.2: United States dollars, two decimal places. Section 2.4: a field that does not match the type and form this contract defines is `400`. The same split that makes a `loss_date` other than `YYYY-MM-DD` a shape error.

**Rejected alternative.**

Accepting (or rounding) the amount would record a figure the caller did not send as two-decimal dollars. There is no section 4 rule for scale, so treating it as admissible content would silently succeed. That is the wrong side of the 2.4 split.

**Contract amended.**

Section 2.2: `estimated_amount` must have exactly two decimal places; any other scale is not well formed. Section 2.4: that case is listed with the other `400` refusals.