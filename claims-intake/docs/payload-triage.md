# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | rejected | W-1 | MALFORMED_REQUEST | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | W-2 | MALFORMED_REQUEST | 400 |
| EDGE-12 | rejected | W-3 | MALFORMED_REQUEST | 400 |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07. `policy_number` is `mot-4471`. The master holds `MOT-4471`.

**The ambiguity.** What the contract failed to determine, and the two readings that were both available. Section 2.2 says `policy_number` is the identifier as held in the policy master. It does not say whether the comparison folds case. Reading A: `mot-4471` is not held, so `V-1` fails with `POLICY_NOT_FOUND`. Reading B: the strings name the same policy, so lookup succeeds and the notification is accepted.

**Decision.** What the service does. Comparison is exact and case-sensitive. EDGE-07 is rejected by `V-1` with `POLICY_NOT_FOUND` and status 422. No later rule runs.

**Authority.** WI-0142 AC-4: a `policy_number` that is not held is `POLICY_NOT_FOUND` and must not be evaluated as if a policy had been found. Product rule in section 2.2: the identifier is the value as held in the policy master, not a folded or trimmed form of what the caller typed.

**Rejected alternative.** The other reading, and why it is wrong rather than merely less preferred. Case-folding to `MOT-4471` and accepting. It is wrong because the master does not hold `mot-4471`, and because a folded match would issue a `claim_reference` keyed to an identifier the portal did not submit. Handlers quote the number they typed. Treating it as a different number is a false statement about their data.

**Contract amended.** Section 4.2: string equality in the rule table is exact and case-sensitive; `V-1` is `policy_number` = policy `policy_number`, with `mot-4471` named as a failing value.

### Decision 2

**Payload.** EDGE-11. `claim_type` is `flood`. `flood` is not in section 2.3.

**The ambiguity.** Section 2.3 fixes the vocabulary. Section 2.4 splits uninterpretable requests (400) from inadmissible content (422). `V-5` refuses a `claim_type` not permitted on the product. Both of these were available: Reading A: `flood` cannot be interpreted as a `claim_type`, so the refusal is 400 before any rule in 4.2. Reading B: the field is a string and is interpreted, then `V-5` returns `TYPE_NOT_COVERED` 422 because `flood` is not in `permitted_claim_types`.

**Decision.** `flood` fails `W-2`. Status 400, `MALFORMED_REQUEST`. `V-5` is not evaluated. `V-5` applies only to a value listed in 2.3.

**Authority.** Product rule in section 2.3: the vocabulary is fixed by this contract; the permitted subset on a product is a property of the policy record and is evaluated by `V-5`. Section 2.4: a value the contract does not define cannot be interpreted (400). `V-5` is not that rule.

**Rejected alternative.** `TYPE_NOT_COVERED` 422. It is wrong because that code tells a handler the product does not cover the peril, which sends them to underwriting. `flood` is not a peril this service names. The portal sent a value the contract does not define, which is the same class of defect as a misspelled field.

**Contract amended.** Section 4.3, check `W-2`: `claim_type` must equal one of the five vocabulary strings, exact and case-sensitive. Section 4.2 note on `V-5`: a non-vocabulary value never reaches `V-5`. Section 5.1: `MALFORMED_REQUEST` `reason` includes `not_in_vocabulary`.

### Decision 3

**Payload.** EDGE-12. `estimated_amount` is `"3499.999"` (three decimal places) on MOT-4476, whose `limit` is `75000.00`.

**The ambiguity.** Section 2.2 requires United States dollars, two decimal places, greater than zero. `"3499.999"` is valid JSON and greater than zero. Reading A: scale other than two means the amount cannot be interpreted as USD to the cent, so the refusal is 400 (`W-3`) and `V-4` is not evaluated. Reading B: the value is a decimal under the limit, so the notification is accepted, possibly after rounding.

**Decision.** Scale must be exactly two. EDGE-12 fails `W-3` with `MALFORMED_REQUEST` and status 400. Nothing is recorded. `V-4` is not evaluated.

**Authority.** Product rule in section 2.2: `estimated_amount` is United States dollars to two decimal places and greater than zero. Section 2.4: a value that cannot be interpreted is 400, not a `V-4` comparison against `limit`.

**Rejected alternative.** Accept, or round to `3500.00` and accept. Accepting is wrong because the service would record an amount the contract said it cannot interpret. Rounding is wrong because it would write a figure the caller did not send, the same class of defect as ignoring an unknown field. Applying `V-4` is also wrong: `V-4` compares an interpreted amount to `limit`, and this amount was never interpreted.

**Contract amended.** Section 4.3, check `W-3`: `estimated_amount` must have decimal scale of exactly two and be greater than zero, with explicit examples (`"3499.999"` fails; `"3499"` fails). Section 5.1: `MALFORMED_REQUEST` `reason` includes `invalid_decimal_scale` and `not_greater_than_zero`.

## Day 2 reconciliation

Section 6 must name every `code` a model refusal can become. The check was: list every constraint on `NotificationRequest` in `src/claims/models.py`, name the 4.3 check it implements, read that check's `code` and status, then confirm the same `code` appears once in section 6. `Policy`, `RecordedNotification`, and `RuleFailure` were listed the same way and then excluded from section 6, because they are not parsed from a portal payload and do not produce an HTTP response on Day 2.

| Model refusal | Check | `code` | Status | In section 6? |
| --- | --- | --- | --- | --- |
| Key not in 2.2, including a misspelling | W-1 | `MALFORMED_REQUEST` | 400 | yes |
| Required field absent (`policy_number`, `loss_date`, `claim_type`, `estimated_amount`) | W-1 | `MALFORMED_REQUEST` | 400 | yes |
| Empty `policy_number`, wrong types, `loss_date` not `YYYY-MM-DD`, `description` not a string or null | W-1 | `MALFORMED_REQUEST` | 400 | yes |
| `claim_type` not one of the five vocabulary strings (`flood`, `Collision`, empty) | W-2 | `MALFORMED_REQUEST` | 400 | yes |
| `estimated_amount` scale not exactly two, or not greater than zero | W-3 | `MALFORMED_REQUEST` | 400 | yes |

Confirmed against the data files: `EDGE-08`, `EDGE-11`, and `EDGE-12` fail at the model (W-1, W-2, W-3). Every other `EDGE-*` payload and every `INVALID-*` payload parses as `NotificationRequest` and is left for the rule table. That matches the classification table above.

`Policy` and `RecordedNotification` constraints (including `cancellation_date` required as `date \| None`, and `claim_reference` matching `CLM-YYYY-NNNNNN`) protect internal objects. They do not add a portal `code`. `RuleFailure` only carries codes that section 6 already lists.

**What was added.** Nothing. Section 6 already maps `MALFORMED_REQUEST` to 400, and every request-facing model refusal is that one code. Splitting W-1 / W-2 / W-3 into three codes would change the contract's 400 envelope; the contract already says those checks share `MALFORMED_REQUEST` and distinguish themselves in `detail.reason` (section 5.1).
