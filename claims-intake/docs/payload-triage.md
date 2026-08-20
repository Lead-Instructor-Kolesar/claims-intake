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
| EDGE-08 | Rejected | -    | INVALID_REQUEST       | 400    |
| EDGE-09 | Rejected | V-5  | TYPE_NOT_COVERED      | 422    |
| EDGE-10 | Rejected | V-7  | POLICY_CANCELLED      | 422    |
| EDGE-11 | Rejected | -    | INVALID_REQUEST       | 400    |
| EDGE-12 | Rejected | -    | INVALID_REQUEST       | 400    |




## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-11

**The ambiguity.** Whether a `claim_type` that does not appear in section 2.3 (for example `flood`) is a business-rule failure under V-5 (`TYPE_NOT_COVERED`) or an uninterpretable request.

**Decision.** Outside the section 2.3 vocabulary is `INVALID_REQUEST` and status 400. V-5 applies only after the value is one of the five defined claim types.

**Authority.** Section 2.4: a request that cannot be interpreted is 400; a request that was interpreted and is not admissible is 422.

**Rejected alternative.** Treating `flood` as `TYPE_NOT_COVERED`. That would imply the type is known to the system and merely not covered by the product.

**Contract amended.** Section 6: `INVALID_REQUEST` covers a `claim_type` outside section 2.3; `TYPE_NOT_COVERED` is limited to vocabulary values not permitted on the product.

### Decision 2

**Payload.** EDGE-04

**The ambiguity.** Whether a loss on the exact cancellation date is covered.

**Decision.** Not covered. V-7 is written with a strict `<`.

**Authority.** WI-0158 AC-2 / product rule PR-19.

**Rejected alternative.** Using `<=`, which would treat the cancellation date as still in cover.

**Contract amended.** Section 4.2 (V-7) and the boundary note under the table.

### Decision 3

**Payload.** EDGE-10

**The ambiguity.** When a policy is both cancelled and past its original expiry date, which error should be returned.

**Decision.** Return `POLICY_CANCELLED` (V-7). Cancellation is listed before expiry in section 4.2, and section 4.1 evaluates in table order.

**Authority.** WI-0158 AC-4.

**Rejected alternative.** Evaluating in identifier order, which would run expiry (V-3) before cancellation (V-7) and return `LOSS_AFTER_EXPIRY`.

**Contract amended.** Section 4.1 (table order, not identifier order) and the listing of V-7 before V-3 in section 4.2.