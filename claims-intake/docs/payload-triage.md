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
| EDGE-08 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-12 | rejected | - | MALFORMED_REQUEST | 400 |

Note: Edge 08/11/12 have malformed payloads that don't get to any of the rules, which is why there is the "-" in the rule section of those rows. This follows acceptance criterion 10.

## Decision log

Three payloads in `data/fnol_edge.json` cannot be classified against the contract as it shipped. Their descriptions in that file name the gap; section 2 of the contract does not close it.

| Payload | What `fnol_edge.json` contains | What the shipped contract left open |
| --- | --- | --- |
| EDGE-07 | `"policy_number": "mot-4471"`, description "Policy number keyed in lower case." The policy master has `MOT-4471`. | Whether V-1 is case-sensitive. |
| EDGE-11 | `"claim_type": "flood"`, description "Claim type is not one of the values the contract defines." Section 2.3 is `collision`, `theft`, `glass`, `liability`, `weather`. | Whether that is 400 or V-5 `TYPE_NOT_COVERED`. |
| EDGE-12 | `"estimated_amount": "3499.999"`, description "Estimated amount carries three decimal places." Section 2.2 requires two decimal places. | Whether that is 400, V-4, or accepted. |

The other nine payloads are classified by rules the contract already stated. EDGE-08 (`estimated_amount` omitted) is 400 under section 2.4 as shipped ("a required field was absent") and is not one of these three.

A decision recorded here and nowhere else has not been made. Each decision below is also in `docs/api-contract.md` section 4.

### Decision 1

**Payload.** EDGE-07 (`data/fnol_edge.json`: `"policy_number": "mot-4471"`, description "Policy number keyed in lower case."). `data/policies.json` holds `MOT-4471`.

**The ambiguity.** `policy_number` is `mot-4471`. The policy master holds `MOT-4471`. Section 2.2 calls it the identifier as held in the policy master, but V-1 only said "exists." One reading treats the strings as the same policy. The other treats them as different identifiers, so the policy is not found.

**Decision.** Rejected. V-1, `POLICY_NOT_FOUND`, 422. Match is exact string equality, including case.

**Authority.** Section 2.2 ("Identifier as held in the policy master") and WI-0142 AC-4: a policy number that is not found returns `POLICY_NOT_FOUND` and is not evaluated against later rules.

**Rejected alternative.** Case-fold and accept against `MOT-4471`. That would record a notification against an identifier the caller did not send, which is the same defect section 2.2 refuses for ignored extra fields. It is also not a 400: the body is intelligible; the data does not match a policy.

**Contract amended.** Section 4.2: V-1 condition is `policy_number` equals a policy master's `policy_number`. Notes: "V-1 is exact string equality with the identifier as held in the policy master. Differing case is not a match (WI-0142, AC-4)."

### Decision 2

**Payload.** EDGE-11 (`data/fnol_edge.json`: `"claim_type": "flood"`, description "Claim type is not one of the values the contract defines."). Section 2.3 vocabulary does not include `flood`.

**The ambiguity.** `claim_type` is `flood`, which is not in the 2.3 vocabulary. One reading is 400: the service cannot interpret it as a claim type. The other is 422 V-5 `TYPE_NOT_COVERED`: it is not permitted on the product.

**Decision.** Rejected. `MALFORMED_REQUEST`, 400. No V-rule runs. `detail.problem` is `value_not_in_vocabulary`.

**Authority.** Section 2.3 (the vocabulary is fixed; V-5 is the permitted subset of that vocabulary) and section 2.4 (400 means the caller's code is wrong). `flood` is not a value this contract defines.

**Rejected alternative.** V-5 `TYPE_NOT_COVERED`. That would make one code mean two things: a vocabulary type the product does not cover (EDGE-09) and a string that is not a claim type at all. V-5 can only run after `claim_type` is one of the 2.3 values.

**Contract amended.** Section 4: "`claim_type` must be one of the values in 2.3. A value that is not in that vocabulary is not a claim type this service can interpret (`problem`: `value_not_in_vocabulary`). V-5 is not applied to it. V-5 evaluates only whether a vocabulary value is permitted on the policy's product." Section 5.2 lists `value_not_in_vocabulary`.

### Decision 3

**Payload.** EDGE-12 (`data/fnol_edge.json`: `"estimated_amount": "3499.999"`, description "Estimated amount carries three decimal places."). Section 2.2 requires two decimal places.

**The ambiguity.** `estimated_amount` is `3499.999`, three decimal places. Section 2.2 requires two. The contract did not say whether that is 400, 422, or accepted (rounded or truncated).

**Decision.** Rejected. `MALFORMED_REQUEST`, 400. No V-rule runs. `detail.problem` is `invalid_scale`.

**Authority.** Section 2.2 (United States dollars, two decimal places) and section 2.4 (400: the body is not intelligible as the decimal this contract defines). V-4 compares magnitude only after the amount is well formed.

**Rejected alternative.** Accept and round, or refuse with V-4 `AMOUNT_EXCEEDS_LIMIT`. Rounding would record an amount the caller did not send. V-4 is a cover check against `limit`, not a format check; using it here would give that code a second meaning.

**Contract amended.** Section 4: "`estimated_amount` must have exactly two decimal places. A value with a different scale is not the decimal this contract defines (`problem`: `invalid_scale`). V-4 is not applied to it. V-4 compares magnitude only, after the amount is well formed." Section 5.2 lists `invalid_scale`.

---

## Day 2 reconciliation: model refusals against section 6

Checked after `NotificationRequest`, `Policy`, and `ClaimRecord` were
implemented. The method was:

1. List every constraint declared on `NotificationRequest` in
   `src/claims/models.py` (`extra="forbid"`, required fields, `min_length`,
   `Literal` vocabulary, `gt=0`, `decimal_places=2`, `date` parse, float
   rejection).
2. Name a payload that triggers each constraint, using the same case ids as
   `tests/unit/test_models.py`.
3. Look up `docs/api-contract.md` section 6 for a code and status for that
   refusal.
4. Check section 5.2 for a `problem` token the HTTP layer can attach when it
   maps the parse refusal. Add any token that was missing.
5. Record what was found, what was added, and what was out of scope.

### Constraint inventory

| Model | Constraint | Payload / case id | Section 6 | Section 5.2 `problem` |
| --- | --- | --- | --- | --- |
| `NotificationRequest` | `extra="forbid"` | `unknown_field`, `misspelled_field` | `MALFORMED_REQUEST` 400 | `unexpected_field` |
| `NotificationRequest` | required fields; no defaults | `missing_policy_number`, `missing_loss_date`, `missing_claim_type`, `missing_estimated_amount`, `missing_estimated_amount_edge_08` | `MALFORMED_REQUEST` 400 | `required_field_absent` |
| `NotificationRequest` | `policy_number` not empty | empty string | `MALFORMED_REQUEST` 400 | `empty_value` |
| `NotificationRequest` | `policy_number` is a string | `policy_number` wrong type | `MALFORMED_REQUEST` 400 | `invalid_type` |
| `NotificationRequest` | `loss_date: date` | `loss_date_wrong_type`, `loss_date_unparsable`, `loss_date_not_iso` | `MALFORMED_REQUEST` 400 | `invalid_type` |
| `NotificationRequest` | `claim_type` is §2.3 vocabulary | EDGE-11 `flood`; `empty_claim_type`; `claim_type_misspelled`; `claim_type` wrong type | `MALFORMED_REQUEST` 400 | `value_not_in_vocabulary` (wrong type: `invalid_type`) |
| `NotificationRequest` | `estimated_amount` `gt=0` | `amount_not_greater_than_zero`; `amount_negative` | `MALFORMED_REQUEST` 400 | `not_greater_than_zero` |
| `NotificationRequest` | two decimal places | EDGE-12; `amount_one_decimal_place`; `amount_integer_scale` | `MALFORMED_REQUEST` 400 | `invalid_scale` |
| `NotificationRequest` | float money rejected | Python `float` | `MALFORMED_REQUEST` 400 | `inexact_money` |
| `NotificationRequest` | `estimated_amount` is decimal | `estimated_amount` wrong type | `MALFORMED_REQUEST` 400 | `invalid_type` |
| `Policy` / `ClaimRecord` | construction constraints | not HTTP payloads | not mapped | not mapped |

### What was found

Section 6 already names `MALFORMED_REQUEST` at 400 for every uninterpretable
request (section 2.4). Every `NotificationRequest` refusal above is that class.
No model-produced *code* was missing, so section 6 was not given a new row.

Section 5.2 named only `required_field_absent`, `invalid_json`,
`value_not_in_vocabulary`, and `invalid_scale`. The inventory needed tokens
for extra fields, empty `policy_number`, wrong type, amount not greater than
zero, and float money. Those tokens were added to section 5.2. They are
`detail.problem` values under the existing `MALFORMED_REQUEST` code, not new
codes.

`Policy` and `ClaimRecord` refusals are in-process construction errors, not
HTTP responses. They do not get their own codes.

### What was added

- `docs/api-contract.md` section 5.2: `unexpected_field`, `empty_value`,
  `invalid_type`, `not_greater_than_zero`, `inexact_money`.
- Section 6: nothing. The code and status were already present.

### Out of scope for this check

Rule codes (`POLICY_NOT_FOUND`, `DUPLICATE_NOTIFICATION`, `POLICY_CANCELLED`,
and the rest of section 4.2) and the policy-master 5xx codes are not produced
by the models. Invalid JSON is produced by the HTTP layer (Day 4), not by
`NotificationRequest`. This note does not claim section 6 is exhaustive for the
whole service; it only confirms that every parse refusal already has a row.
