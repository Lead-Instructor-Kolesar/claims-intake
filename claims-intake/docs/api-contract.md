# Claims Intake Service: API Contract

Version 0.5. Owned by the claims intake team. Consumed by the claims portal team.

Changes in 0.5. Sections 4.1, 4.3, 5 and 6 written. Rules V-6 (WI-0151) and V-7 (WI-0158) added. V-1 restated as an exact, case-sensitive identifier match. Evaluation order is now an explicit sequence and is no longer ascending identifier order; the conflict it resolves is set out in 4.1.2. Well-formedness checks W-1 through W-3 are named so a 400 refusal cites a contract identifier. Adding rules and codes is a compatible change under section 1. The change to evaluation order is not, because it changes which code an existing condition returns, and it is made under a version increment for that reason.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request

### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```

### 2.2 Body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `policy_number` | string | yes | Identifier as held in the policy master. Not empty. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, two decimal places. Greater than zero. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

**`claim_reference`** matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

**`status`** is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation

A request is evaluated in two stages. Stage one decides whether the body
can be interpreted (section 4.3). Stage two decides whether the
interpreted content is admissible (section 4.2). Stage two does not run
if stage one fails. A notification is recorded only if every check in
both stages passes.

Identifiers in this section (`W-1`..`W-3`, `V-1`..`V-7`) name checks.
They are not the evaluation order. The order is section 4.1.

### 4.1 Evaluation order

#### 4.1.1 Sequence

The order is a general rule, not a list of exceptions:

1. Can the body be interpreted? (`W-1`, `W-2`, `W-3`)
2. Does the policy exist? (`V-1`)
3. Is this loss already recorded? (`V-6`)
4. Does cover attach on `loss_date`, walking the policy calendar
   from start to end? (`V-2` inception, then `V-7` cancellation, then
   `V-3` expiry)
5. Do the remaining policy fields admit the content? (`V-4` amount,
   then `V-5` type)

Applied, that is this sequence and no other:

1. `W-1` JSON object, field set, required fields, types
2. `W-2` `claim_type` equals a value listed in section 2.3
3. `W-3` `estimated_amount` scale = 2 AND `estimated_amount` > 0
4. `V-1` `policy_number` = a policy master `policy_number`
5. `V-6` N.`policy_number` = `policy_number` AND N.`loss_date` = `loss_date` AND N.`claim_type` = `claim_type` holds for 0 recorded N
6. `V-2` `loss_date` >= policy `effective_date`
7. `V-7` policy `cancellation_date` is null OR `loss_date` < policy `cancellation_date`
8. `V-3` `loss_date` <= policy `expiry_date`
9. `V-4` `estimated_amount` <= policy `limit`
10. `V-5` `claim_type` = an element of policy `permitted_claim_types`

Evaluation stops at the first check whose condition does not hold. The
caller receives that check's `code` and `status` and no other. Remaining
checks are not evaluated, even when they would also fail. A payload that
violates several rules therefore produces one refusal, and which refusal
it is is determined by this sequence, not by which violation is most
obvious.

Because cover is walked in calendar order, `V-7` precedes `V-3`. A
policy that is both cancelled and out of term returns
`POLICY_CANCELLED`, not `LOSS_AFTER_EXPIRY` (WI-0158, AC-4).

`V-1` is the first check that reads the policy master. If it fails, no
later check runs. Reporting `LOSS_BEFORE_INCEPTION` for a number the
master does not hold is a false statement about the caller's data
(WI-0142, AC-4).

`V-6` runs after `V-1` and before any cover-period check. A retry of an
already recorded notification is `DUPLICATE_NOTIFICATION` even if the
policy would now also fail `V-2`, `V-7`, `V-3`, `V-4`, or `V-5`. The
existing `claim_reference` is the value the handler needs (WI-0151, AC-2).

A request that fails a `W-*` check is refused with status `400` and is
not evaluated against section 4.2. Section 2.4 is the authority for that
split; this sequence is how it is applied.

#### 4.1.2 Why the sequence is not identifier order

The table shipped with `V-1` through `V-5` and the instruction to
evaluate in ascending identifier order. Adding cancellation as `V-7`
under that instruction evaluates `V-3` (`loss_date` <= `expiry_date`)
before `V-7`. A cancelled policy keeps its original `expiry_date`. A
loss on or after `cancellation_date` and also after `expiry_date` would
then return `LOSS_AFTER_EXPIRY`. WI-0158 AC-4 forbids that: the handler
must be told the policy was cancelled, because the other code sends them
to the wrong system.

The identifiers stay with the work items they convert (`V-6` is WI-0151,
`V-7` is WI-0158). Evaluation order is the general rule in 4.1.1: cover
is tested from inception, through cancellation, to expiry. That places
`V-7` between `V-2` and `V-3` for every notification, not as a special
case on one payload. A future rule that also ends cover on a calendar
date belongs in that same walk, not at the end of the identifier list.

### 4.2 Rule table

The condition is what must hold. The `code` and `status` are returned
when it does not. Rows are listed by identifier. Do not evaluate in
table order; evaluate only in the sequence in 4.1. Unqualified field
names on the left of a comparison are request fields. Names qualified
with `policy` are policy-master fields. Names qualified with `N` are
fields of a recorded notification. String equality in this table is
exact and case-sensitive. Date comparisons use the calendar dates as
submitted (`YYYY-MM-DD`).

| ID  | Condition | Code | Status |
| --- | --------- | ---- | ------ |
| V-1 | `policy_number` = policy `policy_number` | `POLICY_NOT_FOUND` | 422 |
| V-2 | `loss_date` >= policy `effective_date` | `LOSS_BEFORE_INCEPTION` | 422 |
| V-3 | `loss_date` <= policy `expiry_date` | `LOSS_AFTER_EXPIRY` | 422 |
| V-4 | `estimated_amount` <= policy `limit` | `AMOUNT_EXCEEDS_LIMIT` | 422 |
| V-5 | `claim_type` = an element of policy `permitted_claim_types` | `TYPE_NOT_COVERED` | 422 |
| V-6 | N.`policy_number` = `policy_number` AND N.`loss_date` = `loss_date` AND N.`claim_type` = `claim_type` holds for 0 recorded N | `DUPLICATE_NOTIFICATION` | 409 |
| V-7 | policy `cancellation_date` is null OR `loss_date` < policy `cancellation_date` | `POLICY_CANCELLED` | 422 |

**`V-1`.** `MOT-4471` is held; `mot-4471` is a different string and the
equality is false. The request value is not trimmed, folded, or
normalised.

**`V-2` and `V-3`.** Inclusive as written. A loss on `effective_date` is
covered (WI-0142, AC-3). A loss on `expiry_date` is covered.

**`V-4`.** Inclusive as written. An amount equal to `limit` is within
cover.

**`V-5`.** Evaluated only after `W-2` has passed. A value that is not in
section 2.3 never reaches `V-5`. The equality is membership: the request
value equals one element of `permitted_claim_types`.

**`V-6`.** The three equalities are the match and the only match
(WI-0151, AC-1). "Holds for 0 recorded N" means no recorded notification
satisfies all three. A refused submission was never recorded, so it is
not an N (WI-0151, AC-3). `description` and `estimated_amount` are not
in the comparison.

**`V-7`.** If `cancellation_date` is null the first disjunct holds and
the rule does not reject (WI-0158, AC-3). If `cancellation_date` is set,
the second disjunct is a strict less-than: `loss_date` <
`cancellation_date` must hold. A loss on the cancellation date is not
covered, because `loss_date` < `cancellation_date` is false when the
dates are equal (WI-0158, AC-1, AC-2). Cancellation takes effect at the
start of that calendar date.

### 4.3 Well-formedness, applied before the rule table

These checks decide whether the body can be interpreted. They are not
business rules. Failure is always `MALFORMED_REQUEST` with status `400`.
The condition is what must hold.

Section 2.4 fixes the split (uninterpretable = 400, inadmissible = 422)
and gives examples of 400. It does not list every 2.2 shape constraint.
A `claim_type` outside the 2.3 vocabulary, and an `estimated_amount`
whose scale is not two or whose value is not greater than zero, are
present and typed but still cannot be interpreted as the fields 2.2
defines. They are 400 (`W-2`, `W-3`), not 422.

| ID  | Condition | Code | Status |
| --- | --------- | ---- | ------ |
| W-1 | the body is a JSON object whose keys are a subset of section 2.2, every required field is present, `description` if present is a string or `null`, `policy_number` is a non-empty string, `loss_date` is a string matching `YYYY-MM-DD`, `claim_type` is a non-empty string, and `estimated_amount` is a number or a string that parses as a decimal | `MALFORMED_REQUEST` | 400 |
| W-2 | `claim_type` = one of `collision`, `theft`, `glass`, `liability`, `weather` | `MALFORMED_REQUEST` | 400 |
| W-3 | `estimated_amount` scale = 2 AND `estimated_amount` > 0 | `MALFORMED_REQUEST` | 400 |

**`W-1`.** A missing required field, a key not listed in 2.2, a value of
the wrong type, invalid JSON, or an empty `policy_number` / `claim_type`
cannot be interpreted. A misspelled key is an unexpected field.

**`W-2`.** Equality is exact and case-sensitive. `flood` is not in the
vocabulary, so the field cannot be interpreted as a `claim_type`. That
is a defect in the caller's code (section 2.4), not a product-coverage
decision. `V-5` answers whether a vocabulary value is permitted on the
policy's product. `Collision` and `COLLISION` fail `W-2` the same way
`flood` does.

**`W-3`.** Scale of exactly two means the submitted value has two digits
after a decimal point, as in `"3499.99"` or `3499.99`. `"3499.999"` and
`3499.999` fail `W-3`. `"3499"` and `3499` fail `W-3`. Zero and negative
amounts fail `W-3`. Scale is a fact about whether the amount can be
interpreted as USD to the cent, not a fact about the policy `limit`.

## 5. Error envelope

Every refusal uses this object and no other:

```
{
  "code":    "<string>",
  "message": "<string>",
  "detail":  { }
}
```

HTTP status is not a field in the body. It is the response status, and
section 6 is the only mapping from `code` to status.

**`code` is a stable promise.** It is one of the values in section 6. It
does not change meaning without a version increment. Callers branch on
`code`. Adding a new `code` is compatible; callers must treat an
unrecognised `code` as a refusal they cannot classify and must not
retry it as if it were a dependency failure.

**`message` is not a stable promise.** It is English for a person. The
service may reword it at any time without a version increment. Callers
must not parse `message`, must not branch on its text, and must not
translate it by matching a known sentence.

**`detail` is an object.** Its keys depend on `code`. Callers may rely
on the keys listed for that `code` in 5.1 being present and of the
stated type. Callers may not rely on: key order; the absence of keys
not listed (new keys may be added and must be ignored); any key that
is listed for a different `code`; any key inside a nested object that
this section does not name. `detail` is never `null`. When a `code`
has no listed keys, `detail` is `{}`.

`detail` carries values that produced the decision. It does not carry
a stack trace, a policy-master URL, or a field the caller did not send
except policy-master fields named in 5.1 and, for `DUPLICATE_NOTIFICATION`,
the `claim_reference` already issued.

### 5.1 `detail` keys the caller may rely on, by `code`

| `code` | Keys present | Types |
| --- | --- | --- |
| `MALFORMED_REQUEST` | `field`, `reason` | string, string |
| `POLICY_NOT_FOUND` | `policy_number` | string |
| `LOSS_BEFORE_INCEPTION` | `policy_number`, `loss_date`, `effective_date` | string, string, string |
| `LOSS_AFTER_EXPIRY` | `policy_number`, `loss_date`, `expiry_date` | string, string, string |
| `POLICY_CANCELLED` | `policy_number`, `loss_date`, `cancellation_date` | string, string, string |
| `AMOUNT_EXCEEDS_LIMIT` | `policy_number`, `estimated_amount`, `limit` | string, string, string |
| `TYPE_NOT_COVERED` | `policy_number`, `claim_type`, `product`, `permitted_claim_types` | string, string, string, array of string |
| `DUPLICATE_NOTIFICATION` | `policy_number`, `loss_date`, `claim_type`, `claim_reference` | string, string, string, string |
| `POLICY_MASTER_TIMEOUT` | `dependency`, `reason` | string, string |
| `POLICY_MASTER_UNREACHABLE` | `dependency`, `reason` | string, string |
| `POLICY_MASTER_UNPARSABLE` | `dependency`, `reason` | string, string |

For `MALFORMED_REQUEST`, `field` is the JSON key at fault, or `""` when
the body is not an object. `reason` is one of: `invalid_json`,
`unexpected_field`, `required_field_absent`, `wrong_type`,
`empty_value`, `invalid_date`, `not_in_vocabulary`, `invalid_decimal_scale`,
`not_greater_than_zero`. Callers may rely on that closed set.

For the three policy-master dependency codes, `dependency` is the
string `policy_master`. `reason` is `timeout`, `unreachable`, or
`unparsable` matching the `code`.

Dates in `detail` are `YYYY-MM-DD`. Decimal values in `detail` are
strings with two decimal places.

### 5.2 Worked examples

The three examples are different failure classes. Their `detail`
objects do not share a shape: compared policy fields, a request-field
defect, and a dependency failure.

**Rule failure.** `POST /notifications` with `policy_number`
`MOT-4493`, `loss_date` `2026-03-02`, `claim_type` `collision`,
`estimated_amount` `"72000.00"`. `V-2` fails. Status `422`.

```
{
  "code": "LOSS_BEFORE_INCEPTION",
  "message": "The loss date is before the policy effective date.",
  "detail": {
    "policy_number": "MOT-4493",
    "loss_date": "2026-03-02",
    "effective_date": "2026-04-15"
  }
}
```

**Request the service could not interpret.** `POST /notifications`
with `policy_number` `MOT-4472`, `loss_date` `2026-03-25`,
`claim_type` `theft`, and no `estimated_amount`. `W-1` fails. Status
`400`.

```
{
  "code": "MALFORMED_REQUEST",
  "message": "The request body could not be interpreted.",
  "detail": {
    "field": "estimated_amount",
    "reason": "required_field_absent"
  }
}
```

**Policy master that did not answer.** `POST /notifications` with a
well-formed body whose `policy_number` is `MOT-4471`. The master does
not return a usable record within the service's time limit. No rule in
4.2 is evaluated. Status `504`.

```
{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond in time.",
  "detail": {
    "dependency": "policy_master",
    "reason": "timeout"
  }
}
```

A policy master that answers and holds no match is not this case. That
is `POLICY_NOT_FOUND`, status `422`, and `detail` contains only
`policy_number`. The caller can correct the number. A timeout cannot
be corrected by changing the payload, which is why the `detail` names
a dependency rather than a field.

## 6. Status code mapping

Every `code` this service produces appears once. Each maps to exactly
one status. Two codes are never used for the same condition.

| `code` | Status | When |
| --- | --- | --- |
| `MALFORMED_REQUEST` | 400 | Stage one failed. The body cannot be interpreted. The caller's code is wrong. |
| `DUPLICATE_NOTIFICATION` | 409 | `V-6` failed. A recorded notification already exists for the same `policy_number`, `loss_date`, and `claim_type`. |
| `POLICY_NOT_FOUND` | 422 | The policy master answered. It holds no identifier equal to request `policy_number`. The caller's data is wrong. This is `V-1`, and it is the policy-master "answered, no match" boundary. |
| `LOSS_BEFORE_INCEPTION` | 422 | `V-2` failed. |
| `LOSS_AFTER_EXPIRY` | 422 | `V-3` failed. |
| `AMOUNT_EXCEEDS_LIMIT` | 422 | `V-4` failed. |
| `TYPE_NOT_COVERED` | 422 | `V-5` failed. |
| `POLICY_CANCELLED` | 422 | `V-7` failed. |
| `POLICY_MASTER_UNREACHABLE` | 503 | The policy master could not be contacted. The payload is not implicated. Retry is reasonable. |
| `POLICY_MASTER_UNPARSABLE` | 502 | The policy master responded and the response could not be parsed as a policy record. The payload is not implicated. |
| `POLICY_MASTER_TIMEOUT` | 504 | The policy master was contacted and did not answer within the service's time limit. The payload is not implicated. Retry is reasonable. |

The four policy-master boundary conditions are: answered with no match
(`POLICY_NOT_FOUND`, 422); unreachable (`POLICY_MASTER_UNREACHABLE`,
503); responded but unparsable (`POLICY_MASTER_UNPARSABLE`, 502);
contacted but timed out (`POLICY_MASTER_TIMEOUT`, 504). The last three
are not the caller's fault and are in the 5xx family so that a portal
does not send the handler to edit a payload that was not wrong.

No other status is used for a refusal this contract specifies. Success
is `201` as in section 3.
