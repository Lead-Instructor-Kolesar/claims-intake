# Claims Intake Service: API Contract

Version 0.4. Owned by the claims intake team. Consumed by the claims portal team.

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

Section 2.4 is applied before any rule in 4.2. A request that is not
well formed returns `MALFORMED_REQUEST` (400) and no V-rule is
evaluated.

These three sentences close gaps that section 2 left open. They are
the decisions recorded for EDGE-07, EDGE-11, and EDGE-12 in
`docs/payload-triage.md`.

`policy_number` is compared by exact string equality with the
identifier held in the policy master. `mot-4471` and `MOT-4471` are
not the same identifier (EDGE-07). Differing case is not a match
(WI-0142, AC-4). V-1 fails; later rules are not evaluated.

`claim_type` must be one of the values in 2.3. `flood` is not in that
vocabulary (EDGE-11). It is not a claim type this service can
interpret (`problem`: `value_not_in_vocabulary`). V-5 is not applied
to it. V-5 evaluates only whether a vocabulary value is permitted on
the policy's product.

`estimated_amount` must have exactly two decimal places. `3499.999`
does not (EDGE-12). A value with a different scale is not the decimal
this contract defines (`problem`: `invalid_scale`). V-4 is not applied
to it. V-4 compares magnitude only, after the amount is well formed.

### 4.1 Evaluation order

Rules are evaluated in the following sequence:

V-1, V-2, V-7, V-3, V-4, V-5, V-6.

Evaluation stops at the first failure. In other words, when more than one rule is violated, the one that comes first in the evaluation sequence ends the evaluation sequence and returns the failure in an error envelope.

V-1 short 
circuits:
if it fails, no rule that reads a policy field is evaluated.

V-7 is evaluated before V-3 because a cancelled policy keeps its original
`expiry_date`. Cover has ended, but the term window is still on the
record. Ascending identifier order would report `LOSS_AFTER_EXPIRY` for a loss
that is both cancelled and out of term. That reason sends the handler
to the wrong system (WI-0158, AC-4).


### 4.2 Rule table

| ID  | Condition                                      | Code                    | Status |
| --- | ---------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` equals a policy master's `policy_number` | `POLICY_NOT_FOUND` | 422    |
| V-2 | `loss_date` >= policy `effective_date`         | `LOSS_BEFORE_INCEPTION` | 422    |
| V-3 | `loss_date` <= policy `expiry_date`            | `LOSS_AFTER_EXPIRY`     | 422    |
| V-4 | `estimated_amount` <= policy `limit`           | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| V-5 | `claim_type` permitted on the policy's product | `TYPE_NOT_COVERED`      | 422    |
| V-6 | `(policy_number, loss_date, claim_type)` is unmatched in recorded notifications | `DUPLICATE_NOTIFICATION` | 409    |
| V-7 | `loss_date` < policy `cancellation_date`       | `POLICY_CANCELLED`      | 422    |

Boundaries are inclusive as written. A loss on the inception date is
covered (WI-0142, AC-3). An amount equal to the limit is within cover.
A prior submission that was rejected is not a duplicate (WI-0151, AC-3).
A loss on the cancellation date is not covered (WI-0158, AC-2).
When `cancellation_date` is null the policy is not cancelled and V-7
is not applied (WI-0158, AC-3).
V-1 is exact string equality with the identifier as held in the policy
master. Differing case is not a match (WI-0142, AC-4).

## 5. Error envelope

Every non-2xx response returns this JSON object and no other:

```
{
  "code": "string",
  "message": "string",
  "detail": {}
}
```

`detail` is always an object, never an array, a string, or null.

**`code`** is stable. Callers branch on it. A code's meaning does not
change. Adding a code is compatible: callers that do not recognize it
fall through to default handling. Redefining a code is not compatible.

**`message`** is not stable. It is for display to a person and may be
reworded on any day. Callers must not parse it, match on it, or branch
on it.

**`detail`** carries the values the decision was made on. Its keys
depend on `code` and are listed per code in section 6.

Callers **may** rely on the three top-level keys on every error; the
meaning of `code`, inside `detail`, only the keys section 6 lists for
that specific `code`.

Callers **may not** rely on: the wording of `message`, any `detail` key
that section 6 does not list for that `code`, a key that appears for
one code existing for another. `rule` is not on every error. Neither
is `field` or `dependency`. Unknown keys at the top level or inside
`detail`, must be ignored.

A rule failure is produced by
section 4 after the request was understood. An uninterpretable request
is produced by section 2.4 before any rule runs. A policy-master
failure is produced when the dependency does not return a usable
policy record.

### 5.1 Rule failure

A recorded duplicate (V-6). Produced by the rule table. `detail`
includes `rule` and the existing `claim_reference` (WI-0151, AC-2).

```
409 Conflict

{
  "code": "DUPLICATE_NOTIFICATION",
  "message": "A notification for this loss event is already recorded.",
  "detail": {
    "rule": "V-6",
    "claim_reference": "CLM-2026-000317",
    "policy_number": "MOT-4471",
    "loss_date": "2026-04-02",
    "claim_type": "collision"
  }
}
```

### 5.2 Request the service could not interpret

A required field is absent. Produced by request parsing. No rule ran,
so `detail` has no `rule` and no policy fields. `problem` is a stable
token for this code; it is not prose.

```
400 Bad Request

{
  "code": "MALFORMED_REQUEST",
  "message": "Required field estimated_amount is absent.",
  "detail": {
    "field": "estimated_amount",
    "problem": "required_field_absent"
  }
}
```

When the body is not valid JSON, `field` is omitted and `problem` is
`invalid_json`. A `claim_type` not in 2.3 has `problem`
`value_not_in_vocabulary`. An `estimated_amount` that is not exactly
two decimal places has `problem` `invalid_scale`.

### 5.3 Policy master that did not answer

A lookup timed out. Produced by the policy-master client. The caller's
payload was not at issue, so `detail` has no `rule` and no `problem`.
It names the dependency and the wait that expired.

```
504 Gateway Timeout

{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond in time.",
  "detail": {
    "dependency": "policy_master",
    "timeout_ms": 2000
  }
}
```

`POLICY_MASTER_UNREACHABLE` and `POLICY_MASTER_INVALID_RESPONSE` also
carry `dependency`. They do not carry `timeout_ms`.

## 6. Status code mapping

Every failure this service produces is in this table. Each code maps
to exactly one status. No two codes mean the same condition.

Status is chosen by what the caller should do next. If the caller must
change the request before trying again, the status is 4xx. If the
caller may send the identical request again and it might succeed, the
status is 5xx.

| Code | Status | Why this status |
| --- | --- | --- |
| `MALFORMED_REQUEST` | 400 | The body was not intelligible. The portal code is wrong. |
| `DUPLICATE_NOTIFICATION` | 409 | A claim record already exists. Creating another is the defect. |
| `POLICY_NOT_FOUND` | 422 | The policy master answered: this number does not exist. The caller's data is wrong. |
| `LOSS_BEFORE_INCEPTION` | 422 | The request was understood. Cover had not attached. |
| `LOSS_AFTER_EXPIRY` | 422 | The request was understood. The original term had ended. |
| `POLICY_CANCELLED` | 422 | The request was understood. Cover ended by cancellation. |
| `AMOUNT_EXCEEDS_LIMIT` | 422 | The request was understood. The estimate is above the limit. |
| `TYPE_NOT_COVERED` | 422 | The request was understood. This type is not on the product. |
| `INTERNAL_ERROR` | 500 | This service failed. The payload is not at issue. Retry may succeed. |
| `POLICY_MASTER_INVALID_RESPONSE` | 502 | The policy master answered; this service could not parse it. Retry may succeed. |
| `POLICY_MASTER_UNREACHABLE` | 503 | The policy master could not be reached. Retry may succeed. |
| `POLICY_MASTER_TIMEOUT` | 504 | The policy master did not answer in time. Retry may succeed. |

Promised `detail` keys for each code. Callers may rely on these keys
for that code and no others.

| Code | Promised `detail` keys |
| --- | --- |
| `MALFORMED_REQUEST` | `problem`; `field` when a field is implicated |
| `DUPLICATE_NOTIFICATION` | `rule`, `claim_reference`, `policy_number`, `loss_date`, `claim_type` |
| `POLICY_NOT_FOUND` | `rule`, `policy_number` |
| `LOSS_BEFORE_INCEPTION` | `rule`, `loss_date`, `effective_date` |
| `LOSS_AFTER_EXPIRY` | `rule`, `loss_date`, `expiry_date` |
| `POLICY_CANCELLED` | `rule`, `loss_date`, `cancellation_date` |
| `AMOUNT_EXCEEDS_LIMIT` | `rule`, `estimated_amount`, `limit` |
| `TYPE_NOT_COVERED` | `rule`, `claim_type`, `product` |
| `INTERNAL_ERROR` | `service` |
| `POLICY_MASTER_INVALID_RESPONSE` | `dependency` |
| `POLICY_MASTER_UNREACHABLE` | `dependency` |
| `POLICY_MASTER_TIMEOUT` | `dependency`, `timeout_ms` |
