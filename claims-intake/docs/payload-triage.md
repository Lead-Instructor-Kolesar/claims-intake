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

**Payload.** EDGE-07

**The ambiguity.** Whether a `policy_number` that differs from the master only in case (`mot-4471` versus `MOT-4471`) is the same identifier.

**Decision.** Match is case-sensitive. `mot-4471` does not exist in the policy master. V-1 fails with `POLICY_NOT_FOUND` and status 422.

**Authority.** Section 2.2: `policy_number` is the identifier as held in the policy master. V-1 tests existence of that identifier. Section 2.4: the request was interpreted; the data is not admissible.

**Rejected alternative.** Case-insensitive lookup, which would treat `mot-4471` as `MOT-4471` and evaluate the remaining rules.

**Contract amended.** Section 2.2 (`policy_number` notes), V-1, and section 6: lookup is an exact, case-sensitive match.

### Decision 3

**Payload.** EDGE-12

**The ambiguity.** Whether an `estimated_amount` with three decimal places (`3499.999`) is rounded or truncated to two places, or cannot be interpreted.

**Decision.** More than two decimal places is `INVALID_REQUEST` and status 400. The service does not round or truncate.

**Authority.** Section 2.2: `estimated_amount` is United States dollars, two decimal places. Section 2.4: a field that carries a value of the wrong type cannot be interpreted and is 400.

**Rejected alternative.** Rounding `3499.999` to `3500.00` (or truncating to `3499.99`) and continuing to the rule table.

**Contract amended.** Section 2.2 (`estimated_amount` notes) and section 6: more than two decimal places is `INVALID_REQUEST`.

## Day 2 reconciliation

Nothing missing from section 6. Every `NotificationRequest` refusal is already `INVALID_REQUEST` (400).

Checked by running `tests/unit/test_models.py` against section 6.