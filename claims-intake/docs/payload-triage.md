# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome  | Rule  | Code                    | Status |
| ------- | -------- | ----- | ----------------------- | ------ |
| EDGE-01 | Accepted | -     | -                       | 201    |
| EDGE-02 | Accepted | -     | -                       | 201    |
| EDGE-03 | Accepted | -     | -                       | 201    |
| EDGE-04 | Rejected | `V-7` | `POLICY_CANCELLED`      | 422    |
| EDGE-05 | Rejected | `V-2` | `LOSS_BEFORE_INCEPTION` | 422    |
| EDGE-06 | Rejected | `V-4` | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| EDGE-07 | Rejected | `V-1` | `POLICY_NOT_FOUND`      | 422    |
| EDGE-08 | Rejected | `V-0` | `SCHEMA_INVALID`        | 400    |
| EDGE-09 | Rejected | `V-5` | `TYPE_NOT_COVERED`      | 422    |
| EDGE-10 | Rejected | `V-7` | `POLICY_CANCELLED`      | 422    |
| EDGE-11 | Rejected | `V-0` | `SCHEMA_INVALID`        | 400    |
| EDGE-12 | Rejected | `V-0` | `SCHEMA_INVALID`        | 400    |

Every rule identifier above is defined in `docs/api-contract.md`: `V-0` in section 4.3, `V-1` through `V-7` in the table in section 4.2. Every code above appears in the mapping in section 6.

## Working, payload by payload

Each line states the policy record read and the stage of section 4.1 at which evaluation stopped.

**EDGE-01.** `MOT-4479`, `effective_date` 2026-03-15. `loss_date` 2026-03-15 equals inception, and `V-2` is inclusive, so cover attaches on the day (WI-0142, AC-3). `cancellation_date` is `null`, so `V-7` does not apply. 5000.00 <= limit 55000.00. `collision` is permitted on `personal_auto_standard`. No prior recorded notification. Recorded, 201.

**EDGE-02.** `MOT-4501`, limit 50000.00. `estimated_amount` 50000.00 equals the limit and `V-4` is inclusive, so the amount is within cover. 2026-06-04 falls inside 2026-01-01 to 2026-12-31. `cancellation_date` is `null`. Recorded, 201.

**EDGE-03.** `MOT-4489`, `expiry_date` 2026-02-28. `loss_date` 2026-02-28 equals expiry and `V-3` is inclusive, so the final day of the term is covered. `cancellation_date` is `null`, so the policy ran to its stated end. 9000.00 <= 50000.00, `theft` permitted. Recorded, 201.

**EDGE-04.** `MOT-4497`, `cancellation_date` 2026-01-15. `loss_date` 2026-01-15 is not strictly earlier than the cancellation date, so `V-7` fails on the boundary the contract states explicitly (WI-0158, AC-2). This is the only rule violated: the loss falls inside the original term (2025-06-01 to 2026-05-31), 480.00 is well under the 50000.00 limit, and `glass` is permitted. Rejected at stage 2, `POLICY_CANCELLED`, 422.

**EDGE-05.** `MOT-4493`, `effective_date` 2026-04-15, limit 50000.00. Two rules are violated: `loss_date` 2026-03-02 precedes inception (`V-2`) and 72000.00 exceeds the limit (`V-4`). `V-2` is in stage 3 and `V-4` is in stage 4, so the caller is told about inception. Rejected, `LOSS_BEFORE_INCEPTION`, 422. This is the classification the stated order requires, not the one that lists both faults.

**EDGE-06.** `MOT-4502`, limit 10000.00. In term (2026-02-01 to 2027-01-31), not cancelled, and `collision` is permitted on the product, so `V-5` does not fire. 26000.00 > 10000.00. Rejected at stage 4, `AMOUNT_EXCEEDS_LIMIT`, 422.

**EDGE-07.** `mot-4471` in lower case. Under determination D-1 the value is looked up unnormalised, the policy master holds `MOT-4471` and reports no match, and section 6.3 maps "answered, no match" to `V-1`. Rejected, `POLICY_NOT_FOUND`, 422. `V-1` short circuits, so no policy field is compared and the fact that the loss and amount would otherwise have passed against `MOT-4471` is never reached. See Decision 1.

**EDGE-08.** `estimated_amount` is absent, and section 2.2 makes it required. Stage 0 violation 1. No policy is read. Rejected, `SCHEMA_INVALID`, 400, with `detail.violations` naming `estimated_amount` as a required field absent. This payload is determined by the contract as it shipped (section 2.4) and needed no new decision.

**EDGE-09.** `MOT-4481`, product `personal_auto_named_perils`, `permitted_claim_types` are `theft`, `glass`, `weather`, `liability`. `collision` is inside the section 2.3 vocabulary, so stage 0 passes; it is not a member of `permitted_claim_types`, so `V-5` fails. In term (2026-02-15 to 2027-02-14) and 4800.00 <= 30000.00, so `V-4` does not fire first. Rejected, `TYPE_NOT_COVERED`, 422.

**EDGE-10.** `MOT-4500`, `cancellation_date` 2025-10-01, `expiry_date` 2025-12-31. `loss_date` 2026-01-08 violates `V-7` and `V-3` together. The staged order in section 4.1 puts `V-7` in stage 2 and `V-3` in stage 3, so the caller receives `POLICY_CANCELLED`, which is what WI-0158 AC-4 requires. Rejected, 422. Under the ascending-identifier order that version 0.4 shipped with, this payload would have returned `LOSS_AFTER_EXPIRY` and the contract would have violated its own acceptance criterion.

**EDGE-11.** `claim_type` is `flood`, which is not one of the five values in section 2.3. Under determination D-2 this is a stage 0 violation, refused before any policy is read. Rejected, `SCHEMA_INVALID`, 400. `MOT-4471` exists and the loss and amount would have passed, but stage 0 is never left. See Decision 2.

**EDGE-12.** `estimated_amount` is `3499.999`, three decimal places against the two that section 2.2 specifies. Under determination D-3 the scale is part of the type and the service does not round. Stage 0 violation 7. Rejected, `SCHEMA_INVALID`, 400. See Decision 3.

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07, `policy_number` `mot-4471` against a policy master that holds `MOT-4471`.

**The ambiguity.** The contract said nothing about how `policy_number` is compared to the policy master. Section 2.2 described the field as the "identifier as held in the policy master" and required it to be a non-empty string, and `V-1` required that it "exists in the policy master", but neither said whether existence is decided by an exact comparison or a normalised one. Both readings were available and neither was strained. Read as a caller obligation, `mot-4471` is not the identifier as held and no policy exists, so `V-1` fails with `POLICY_NOT_FOUND` (422). Read as a description of intent, the caller plainly meant `MOT-4471`, the service should upper-case before lookup, and the notification is accepted with 201. The gap mattered because the two readings differ by the whole outcome — a refusal against a recorded claim — and because an implementer would have picked one silently in an afternoon without noticing there was a choice.

**Decision.** `policy_number` is compared to the policy master exactly as sent, byte for byte and case sensitively. The service performs no upper-casing, trimming, or other normalisation before lookup, and `V-6` matches on the same unnormalised value. `mot-4471` reaches the master unchanged, the master reports no match, and the caller receives `POLICY_NOT_FOUND` with status 422.

**Authority.** Section 2.2 defines the field as the "identifier as held in the policy master", which places the obligation on the caller to send the value as it is held. Section 1 states that the policy master is a dependency this service reads and does not own, so a rule about which strings denote the same policy is not this service's to invent. WI-0151 AC-1 supplies the decisive constraint: the duplicate key is `policy_number`, `loss_date` and `claim_type`, so a matching rule for identity has to be one rule used consistently in both places.

**Rejected alternative.** Normalise `policy_number` to upper case before lookup, accepting EDGE-07 with 201. This is wrong rather than merely less convenient, for two reasons. First, it makes the intake service the author of a policy-identity rule that belongs to the policy master, and it does so invisibly: the moment the master begins issuing identifiers whose case is significant, or identifiers that differ only in punctuation, the service's normalisation silently maps two distinct policies onto one and a notification is recorded against the wrong contract of insurance. Nothing in the intake service would detect that. Second, the normalisation cannot be confined to `V-1`. Unless the identical transformation is also applied to the `V-6` duplicate key, `MOT-4471` and `mot-4471` submitted for the same loss are two different keys, no duplicate is found, and two claim records exist for one loss event — the exact defect WI-0151 was raised to stop, reintroduced through a rule intended to be helpful. A reading that requires a second, unstated rule elsewhere in the contract to avoid breaking an acceptance criterion is not the reading the contract supports.

**Contract amended.** Section 4.2, final paragraph of the boundaries block, states that `policy_number` is compared exactly and case sensitively in both `V-1` and `V-6`, and gives `mot-4471` against `MOT-4471` as the worked case. Recorded as determination **D-1** in section 4.4 with the reasoning above.

### Decision 2

**Payload.** EDGE-11, `claim_type` of `flood`.

**The ambiguity.** `flood` is a string, so it satisfies the type given in section 2.2, but it is not one of the five values in the section 2.3 vocabulary. The contract had two places that could each claim the value and did not say which one owns it. Section 2.2 said `claim_type` must be "one of the values in 2.3", which makes the vocabulary part of the request shape and points at a 400 for a request that could not be interpreted (section 2.4). Section 4.2 `V-5` said `claim_type` must be "permitted on the policy's product", and `flood` is permitted on no product, which points at `TYPE_NOT_COVERED` and 422. The two readings differ in status, in whether a policy is read at all, and in who is expected to act on the result, so the payload could not be classified until one of them was chosen.

**Decision.** A `claim_type` outside the section 2.3 vocabulary fails stage 0 (`V-0`) and is refused with `SCHEMA_INVALID` and status 400, before any policy is read. `V-5` and `TYPE_NOT_COVERED` are reserved for a value inside the vocabulary that the policy's product does not permit. EDGE-11 is therefore 400, and the fact that `MOT-4471` exists and would have passed every other rule is never reached.

**Authority.** Section 2.3 states that "the vocabulary is fixed by this contract", which makes membership of the vocabulary a property of the request and not of any policy. The same paragraph draws the line explicitly: "the permitted subset is a property of the policy record and is evaluated by rule `V-5`" — the subset, of a fixed set, which presupposes the value is in the set. Section 2.4 assigns a request the service cannot interpret to 400 and says the caller's code is wrong, which is what an out-of-vocabulary value is: the portal builds `claim_type` from a fixed list, so `flood` means the portal has drifted from the contract.

**Rejected alternative.** Refuse EDGE-11 under `V-5` with `TYPE_NOT_COVERED` and 422. This is wrong because the response would be a false statement. `TYPE_NOT_COVERED` asserts something about the policy — that this product does not extend to this peril — and it is accompanied in section 6.2 by the product's `permitted_claim_types`, which invites the handler to compare. For `flood` there is nothing to compare: no product in the policy master permits it, because the service does not recognise it as a peril at all. The handler is sent to underwriting to ask for an endorsement that could not be written, when the actual fault is in the portal's code and only a developer can clear it. It also inverts the section 2.4 split, which the contract states holds "without exception": it would return 422, meaning the caller's data is wrong and a person needs to see the reason, for a fault no person handling the claim can do anything about. Finally it would require reading a policy record to answer a question about the request shape, which is work the service can prove is unnecessary before it starts.

**Contract amended.** Section 4.3 lists an out-of-vocabulary `claim_type` as stage 0 violation 6. Section 4.4 records it as determination **D-2**, including the statement that `TYPE_NOT_COVERED` applies only to a value inside the section 2.3 vocabulary. Section 5.4 example 2 shows the `detail.violations` entry the caller receives, quoting the five permitted values.

### Decision 3

**Payload.** EDGE-12, `estimated_amount` of `3499.999`.

**The ambiguity.** Section 2.2 gave `estimated_amount` as "decimal, United States dollars, two decimal places. Greater than zero." It did not say whether "two decimal places" is a constraint the service enforces on input or a description of how money is represented, and the contract stated no consequence for a value with a different scale. Three readings were available: refuse the request as uninterpretable (400), round or truncate to two places and continue evaluating with the adjusted value (which here yields 3500.00, within the 75000.00 limit, and 201), or treat the scale as a content problem and refuse with 422. Nothing in the document ruled any of them out, so the payload had no determined outcome.

**Decision.** `estimated_amount` must carry no more than two decimal places. A value with a finer scale fails stage 0 (`V-0`) and is refused with `SCHEMA_INVALID` and status 400. The service does not round, truncate, or otherwise adjust a monetary value. EDGE-12 is refused at 400 and `MOT-4476` is never read.

**Authority.** Section 2.2 states the scale in the same cell as the type and alongside "greater than zero", which places it among the constraints that describe a well formed value rather than among the business rules in section 4; section 2.4 assigns a field carrying a value the contract does not define to 400. The controlling reasoning is section 2.2's own, given for undefined fields: accepting the payload with the field ignored "would record a notification built from data the caller did not send". Adjusting a value the caller did send is the same defect reached by a different route.

**Rejected alternative.** Round to the nearest cent and accept, recording 3500.00. This is wrong for a reason stronger than preference: the service would write a monetary figure that no caller ever submitted, and `estimated_amount` is not decoration. It is the figure `V-4` is compared against, and it is the figure downstream reserving reads. A payload of `3499.999` against a limit of `3500.00` would be accepted after rounding to a value equal to the limit, so rounding does not merely alter a recorded number, it changes which side of a rule boundary a notification falls on — and the direction of rounding was itself unspecified, so two conforming implementations could return 201 and 422 for the identical payload. That is precisely the failure mode this contract exists to prevent. Refusing at 400 costs the caller one corrected submission and leaves the recorded figure exactly what was sent.

**Contract amended.** Section 4.3 lists a scale greater than two decimal places as stage 0 violation 7, and lists a zero or negative amount as violation 8 for the same reason. The same section fixes `estimated_amount` as a JSON string holding a decimal numeral, so that "more than two decimal places" is a test the implementer can apply without inventing a representation. Section 4.4 records the decision and the no-rounding rule as determination **D-3**.

## Day 2 reconciliation: model rejections against section 6

Checked by enumerating every `ValidationError` `NotificationRequest` and `Policy` can raise, mapping each one to a bullet in section 4.3 or to the policy-master boundary in 6.3, and confirming that bullet already has a code and status in section 6. The models do not emit codes themselves; they refuse by failing to construct. The code the service will return is the one section 6 already names for that refusal.

### `NotificationRequest` — every refusal is `V-0` / `SCHEMA_INVALID` / 400

| What the model refuses | Section 4.3 | Section 6.2 |
| --- | --- | --- |
| Required field absent or `null` (`policy_number`, `loss_date`, `claim_type`, `estimated_amount`) | Violation 1 | `SCHEMA_INVALID` 400 |
| Wrong JSON type (including a non-string `policy_number` or `description`) | Violation 2 | `SCHEMA_INVALID` 400 |
| Field not listed in section 2.2 | Violation 3 | `SCHEMA_INVALID` 400 |
| `policy_number` empty or whitespace-only (value not trimmed; D-1) | Violation 4 | `SCHEMA_INVALID` 400 |
| `loss_date` not `YYYY-MM-DD`, or not a real calendar date | Violation 5 | `SCHEMA_INVALID` 400 |
| `claim_type` outside the section 2.3 vocabulary | Violation 6 / D-2 | `SCHEMA_INVALID` 400 |
| `estimated_amount` with more than two decimal places | Violation 7 / D-3 | `SCHEMA_INVALID` 400 |
| `estimated_amount` zero or negative | Violation 8 | `SCHEMA_INVALID` 400 |

`MALFORMED_JSON` is not a model outcome. The body never becomes a dict, so `NotificationRequest` is never asked to parse it. That code stays a transport concern for Day 4 and is already in 6.2.

### `Policy` — unparsable master records are `POLICY_MASTER_INVALID_RESPONSE` / 502

| What the model refuses | Contract home | Section 6.3 |
| --- | --- | --- |
| `cancellation_date` omitted (as opposed to present and `null`) | 4.2 V-7 boundaries, WI-0158 AC-3 | `POLICY_MASTER_INVALID_RESPONSE` 502 |
| Missing required field, extra field, wrong type, or `permitted_claim_types` outside the vocabulary | 6.3 "answered with something the service cannot parse" | `POLICY_MASTER_INVALID_RESPONSE` 502 |

These are not `SCHEMA_INVALID`. The request was well formed; the policy master broke its own record shape.

### What was not a gap

`ClaimRecord` will refuse an ill-formed `claim_reference`. That is an internal invariant on values this service issues (section 3). It is not a caller-facing refusal and does not belong in section 6.

**Result.** Nothing was added to `docs/api-contract.md` section 6. Every refusal the models can produce already has a code and status: request-shape failures as `SCHEMA_INVALID` (400), unparsable policy records as `POLICY_MASTER_INVALID_RESPONSE` (502).

### How the two type-level guarantees were verified

Two of the guarantees this work claims are enforced by the type checker rather than by a test, so asserting them in the test suite would prove nothing: a test can only observe what happens at runtime, and both of these are supposed to fail before the code runs. They were checked by writing a file that deliberately violates each one and confirming `mypy` rejects it. The file is not committed, because a file that fails type checking would stop `mypy` exiting zero.

| Guarantee | The line that must not compile | What mypy reported |
| --- | --- | --- |
| A comparison against `cancellation_date` that does not handle absence fails type checking (WI-0158 AC-3) | `request.loss_date < policy.cancellation_date` | `Unsupported operand types for < ("date" and "None")` |
| A rule identifier can never be passed where an error code is expected | `RuleFailure(rule="POLICY_CANCELLED", code="V-7")` | Both arguments rejected: `rule` expects `Literal["V-0"..."V-7"]`, `code` expects the section 6 enumeration |
| The same transposition is impossible on the path that actually refuses | `ValidationOutcome.failed(rule="POLICY_CANCELLED", code="V-7")` | Both arguments rejected, for the same two reasons |
| A code section 6 does not list cannot be returned at all | `ValidationOutcome.failed(rule="V-7", code="TOTALLY_MADE_UP")` | `code` rejected; the contract enumeration is the type |

The second check found a real defect, and following it up found a larger one.

`RuleFailure` originally declared both fields as `str`, which made the two fields separate in name only: the swapped construction above type-checked and would have reported the rule label `V-7` to a caller branching on `code`. The fields now carry distinct `Literal` types, `RuleId` and `ErrorCode`, drawn from section 4 and section 6 respectively.

That fix alone was not worth much, because the rule engine did not use `RuleFailure`. `ValidationOutcome` stored its own `rule: str | None` and `code: str | None`, so every refusal the service actually produced bypassed the type built to make refusals safe, and the transposition remained available on the only path where it could reach a caller. `ValidationOutcome` now stores a `RuleFailure` and derives `rule` and `code` from it as read-only properties, which keeps the contract vocabulary readable at the call sites while leaving one construction path, typed. Two tests pin this at runtime as well as in the type checker: a refusal carries the expected `RuleFailure`, and a passing outcome carries none.

`ErrorCode` doubles as the enumeration of section 6, so a code the contract does not list is not constructible, and a test asserts the HTTP layer's status mapping covers exactly that set.

### One naming conflict between the starter and the interface contract

The record type is named `ClaimRecord` in the C2 interface contract and `RecordedNotification` in the starter's `models.py` stub, which the shipped `service.py` stub imported. The two cannot both be the name, and the choice is not cosmetic: C2 is the interface Day 3 and Day 4 were written against, so the contract name wins and `ClaimRecord` is what the source and the tests use throughout. `RecordedNotification` stays bound to the same class in `models.py`, so code carrying the starter's signature still resolves rather than failing at import. The alias is the only place in the codebase where the old name appears.

## Day 3 reconciliation: the rule engine against the classification above

Checked by running the rule engine over every payload in all three data files and comparing the rule and code it returned against the classification table at the top of this document. The comparison is not a manual reading: `tests/unit/test_service.py` parametrises on the payload identifier and asserts the rule identifier and the code, so the table and the code cannot drift without a test failing.

| What was checked | How | Outcome |
| --- | --- | --- |
| The rule each rejected payload stops at | Parametrised cases over EDGE-04 through EDGE-10 and INVALID-01 through INVALID-07, asserting `outcome.rule` and `outcome.code` | Matches the table above for every payload |
| The three inclusive boundaries (`V-2`, `V-3`, `V-4`) | Three cases per rule: one unit below, one exactly on, one above | On the boundary is covered, as sections 4.2 and WI-0142 AC-3 require |
| The strict boundary (`V-7`) | Day before cancellation passes, on the date fails, after fails, `null` does not apply | Matches WI-0158 AC-2 and AC-3 |
| Stage order where two rules are violated | EDGE-05 returns `LOSS_BEFORE_INCEPTION` and not `AMOUNT_EXCEEDS_LIMIT`; EDGE-10 returns `POLICY_CANCELLED` and not `LOSS_AFTER_EXPIRY` | Matches section 4.1 and WI-0158 AC-4 |
| The `detail` keys each code carries | One case per code asserting the exact key set against the section 6.2 row | Every documented key present, no undocumented key |

**Two things the rule engine does not decide.** A dependency failure is not caught by `V-1`, so `PolicyLookupFailed` propagates and the HTTP layer chooses between 504, 503 and 502. And no rule reads a status code, because section 6 maps a code to a status at the boundary.

**Result.** No contract change. Section 4 already determined every case the payload files contain, which is what Day 1's three determinations were for.
