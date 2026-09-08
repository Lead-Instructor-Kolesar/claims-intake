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

Checked after `NotificationRequest`, `Policy`, and `RecordedNotification`
were implemented, against the Day 1 contract (sections 4–6 already filled).
The check was: inventory every constraint the models declare, name a payload
that triggers it (the same cases as `tests/unit/test_models.py`), look up
section 6 for a code and status, and close gaps.

### Constraint inventory

| Model | Constraint | Payload / case | Section 6 |
| --- | --- | --- | --- |
| `NotificationRequest` | `extra="forbid"` | extra key; misspelled field | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | required fields; no defaults | field omitted; EDGE-08 | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | `policy_number` not empty | empty string | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | `loss_date: date` | unparsable / wrong type | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | `claim_type` is §2.3 vocabulary | EDGE-11 `flood` | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | `estimated_amount` `gt=0` | `"0.00"`; negative | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | two decimal places (EDGE-12 / §4 `invalid_scale`) | EDGE-12 `"3499.999"` | `MALFORMED_REQUEST` 400 |
| `NotificationRequest` | float money rejected | Python `float` | `MALFORMED_REQUEST` 400 |
| `Policy` / `RecordedNotification` | construction constraints | not HTTP payloads | not mapped |

### What was found

Section 6 already names `MALFORMED_REQUEST` at 400 for every uninterpretable
request. Every `NotificationRequest` refusal above is that class (section 2.4
and section 4's EDGE-11 / EDGE-12 sentences). No model-produced code was
missing. Section 6 was not amended in this check.

`Policy` and `RecordedNotification` refusals are in-process construction
errors, not HTTP responses. They do not get their own codes.

### Out of scope for this check

Rule codes (`POLICY_NOT_FOUND`, `DUPLICATE_NOTIFICATION`, `POLICY_CANCELLED`,
and the rest of section 4.2) and the policy-master 5xx codes are not produced
by the models. This note does not claim section 6 was re-derived from Day 2;
it only confirms that parse refusals already have a row.
