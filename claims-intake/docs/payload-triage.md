# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | refused | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | refused | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | refused | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | refused | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | refused | - | MALFORMED_REQUEST | 400 |
| EDGE-09 | refused | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | refused | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | refused | - | MALFORMED_REQUEST | 400 |
| EDGE-12 | refused | - | MALFORMED_REQUEST | 400 |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07

**The ambiguity.** What the contract failed to determine, and the two readings that were both available.

Section 2.2 calls `policy_number` the "identifier as held in the policy master." V-1 as shipped required that `policy_number` exist in the policy master. Neither said whether `mot-4471` and `MOT-4471` are the same identifier.

- Reading A: the match is exact and case-sensitive. `mot-4471` is not in the master, so V-1 fails.
- Reading B: the match folds case. `mot-4471` locates `MOT-4471` and the remaining rules run.

**Decision.** What the service does.

Match is exact and case-sensitive against the value as stored. EDGE-07 is refused with `POLICY_NOT_FOUND`, status 422. The service does not fold case, trim, or otherwise rewrite the identifier.

**Authority.** The work item, acceptance criterion, or product rule that supports it.

Section 2.2: the identifier is the value as held in the policy master, which is `MOT-4471`. WI-0142 AC-4: a `policy_number` that is not found is rejected with `POLICY_NOT_FOUND` and is not evaluated against later rules. Two strings that differ in case are two identifiers.

**Rejected alternative.** The other reading, and why it is wrong rather than merely less preferred.

Case-insensitive lookup. That would record a notification against a policy number the caller did not send. Section 2.2 already refuses unknown fields for that reason: the service must not record a notification built from data the caller did not send. Folding case is the same rewrite. It would also report that `mot-4471` exists in the master, which is false.

**Contract amended.** Section and what changed.

Section 4.2, V-1. The condition now requires an exact, case-sensitive match against the value as stored.

### Decision 2

**Payload.** EDGE-11

**The ambiguity.**

`claim_type` is `flood`, which is not in the section 2.3 vocabulary. Section 2.2 says the field is "one of the values in 2.3." Section 2.3 says the vocabulary is fixed by this contract and that V-5 evaluates the permitted subset. Section 2.4 splits 400 (cannot be interpreted) from 422 (interpreted but not admissible).

- Reading A: `flood` cannot be interpreted as a `claim_type` this contract defines, so the request is refused with status 400 before any rule runs.
- Reading B: `flood` is a string, so the request is well formed, and V-5 refuses it as `TYPE_NOT_COVERED` because it is not permitted on the product.

**Decision.**

`flood` is uninterpretable. Refused with `MALFORMED_REQUEST`, status 400, before any rule in section 4.2 is evaluated. V-5 is never reached.

**Authority.**

Section 2.4: a request that cannot be interpreted is 400, and that split holds without exception. The caller's code is wrong. Section 2.3: the vocabulary is fixed by this contract; V-5 evaluates which of those values the product permits. A string outside the vocabulary is not a coverage question.

**Rejected alternative.**

Treating `flood` as V-5 `TYPE_NOT_COVERED`. That reports a fact about the policy's product for a claim type the service does not have. `TYPE_NOT_COVERED` tells a handler to look at the product; the defect is that the portal sent a value this contract does not define. It would also require a policy lookup to refuse a payload that is already wrong without one.

**Contract amended.**

Section 4.1. A `claim_type` not in the section 2.3 vocabulary is refused with status 400 before any rule in the table is evaluated.

### Decision 3

**Payload.** EDGE-12

**The ambiguity.**

`estimated_amount` is `3499.999`, three decimal places. Section 2.2 says United States dollars, two decimal places. It does not say what happens when more than two arrive.

- Reading A: more than two decimal places cannot be interpreted as the amount this contract defines, so the request is refused with status 400 before any rule runs.
- Reading B: the value is a decimal, so it is well formed; round or truncate to two places and evaluate the rules. This amount is within the policy limit, so the notification would be accepted.

**Decision.**

More than two decimal places is uninterpretable. Refused with `MALFORMED_REQUEST`, status 400, before any rule in section 4.2 is evaluated. The service does not round, truncate, or otherwise rewrite the amount.

**Authority.**

Section 2.2: two decimal places is a constraint on the field. Section 2.4: a field that does not carry a value of the type this contract defines cannot be interpreted; the caller's code is wrong. United States dollars to two places is that type.

**Rejected alternative.**

Rounding or truncating to `3500.00` or `3499.99` and accepting. Either rewrite records a notification built from an amount the caller did not send, which section 2.2 already forbids for unknown fields. Rounding and truncating also disagree with each other, so accepting would invent the amount. Evaluating `3499.999` against V-4 would treat a malformed amount as admissible content.

**Contract amended.**

Section 4.1. An `estimated_amount` carrying more than two decimal places is refused with status 400 before any rule in the table is evaluated.

## Reconciliation (Day 2)

Compared every rejection `NotificationRequest` and `Policy` can produce against contract section 6.

The model refuses extra fields, missing required fields, empty `policy_number`, dates that are not `YYYY-MM-DD`, `claim_type` values outside the section 2.3 vocabulary, `estimated_amount` values that are not a decimal, not greater than zero, or carry more than two decimal places. Each of those is uninterpretable and becomes `MALFORMED_REQUEST` / 400. Section 6 already had that code. No new code was added.

Checked by listing each `ValidationError` case in `tests/unit/test_models.py` and asking whether section 6 already named a code for it. Rule failures, duplicates, and policy-master dependency failures are not model rejections; they already had rows.

Section 4.1 now also names the empty `policy_number` and non-positive `estimated_amount` cases as 400 before any rule, so they cannot be read as `POLICY_NOT_FOUND` or as a new 422. Section 6's `MALFORMED_REQUEST` cause was updated to cite sections 2.4 and 4.1.
