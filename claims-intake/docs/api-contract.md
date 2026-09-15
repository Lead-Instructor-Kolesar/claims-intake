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
| `policy_number` | string | yes | Identifier as held in the policy master. Not empty. Matched exactly, including case. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, exactly two decimal places. Greater than zero. A value with any other scale is not well formed. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

A `claim_type` that is not one of these values cannot be interpreted and is refused with status `400` and code `MALFORMED_REQUEST` under section 2.4. The vocabulary is fixed by this contract. Which of these values are admissible on a given notification depends on the product the policy is written on. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400` and code `MALFORMED_REQUEST`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, a field was present that this contract does not define, `claim_type` was not one of the values in 2.3, or `estimated_amount` did not have exactly two decimal places. The caller's code is wrong.

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

### 4.1 Evaluation order

Rules are evaluated in the order they appear in the table below.
Evaluation stops at the first failure and that rule's code is returned.
V-1 is evaluated first and short circuits: if it fails, no rule that
reads a policy field is evaluated (WI-0142, AC-4). V-7 is evaluated
before V-3: a cancelled policy whose loss also falls after the original
expiry is reported as `POLICY_CANCELLED`, not `LOSS_AFTER_EXPIRY`
(WI-0158, AC-4). 

### 4.2 Rule table

| ID  | Condition                                      | Code                    | Status |
| --- | ---------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` exists in the policy master    | `POLICY_NOT_FOUND`      | 422    |
| V-6 | count of recorded notifications with this `policy_number`, `loss_date`, and `claim_type` = 0 | `DUPLICATE_NOTIFICATION`      | 409    |
| V-2 | `loss_date` >= policy `effective_date`         | `LOSS_BEFORE_INCEPTION` | 422    |
| V-7 | policy `cancellation_date` is null or `loss_date` < policy `cancellation_date` | `POLICY_CANCELLED`      | 422    |
| V-3 | `loss_date` <= policy `expiry_date`            | `LOSS_AFTER_EXPIRY`     | 422    |
| V-5 | `claim_type` permitted on the policy's product | `TYPE_NOT_COVERED`      | 422    |
| V-4 | `estimated_amount` <= policy `limit`           | `AMOUNT_EXCEEDS_LIMIT`  | 422    |


Boundaries are inclusive as written for `>=` and `<=`. A loss on the
inception date is covered (WI-0142, AC-3). An amount equal to the limit
is within cover. V-7 uses `<`: a loss on the cancellation date is not
covered (WI-0158, AC-2). V-6 matches recorded notifications only
(WI-0151, AC-3). On `DUPLICATE_NOTIFICATION`, `detail` includes the
existing `claim_reference` (WI-0151, AC-2).

## 5. Error envelope

Every non-2xx response is a JSON object with exactly three keys: `code`,
`message`, and `detail`. No other shape is used.

**Stable.** `code` is a promise. Callers branch on it. Adding a new code
is compatible. Changing the meaning of a code, removing a code, or
changing the status mapped to a code in section 6 is not. The three keys
are always present.

**Unstable.** `message` is for display. It may change without notice.
Callers must not parse it or branch on it.

**`detail`.** Always an object. Its keys depend on `code`. A caller may
rely on the keys listed for that `code` in the table below. A caller may
not assume that a key present for one code is present for another, may
not require a key this table does not list, and must ignore keys they
do not recognize. `rule` appears only for a section 4 refusal. A body
the service could not interpret, and a policy master that did not
answer, have no `rule` because no rule ran.

| Code | Keys in `detail` a caller may rely on |
| --- | --- |
| `MALFORMED_REQUEST` | `field` — the body field that could not be interpreted, when one field is at fault. Absent when the body is not valid JSON. |
| `POLICY_NOT_FOUND` | `rule`, `policy_number` |
| `LOSS_BEFORE_INCEPTION` | `rule`, `loss_date`, `effective_date` |
| `POLICY_CANCELLED` | `rule`, `loss_date`, `cancellation_date` |
| `LOSS_AFTER_EXPIRY` | `rule`, `loss_date`, `expiry_date` |
| `TYPE_NOT_COVERED` | `rule`, `claim_type` |
| `AMOUNT_EXCEEDS_LIMIT` | `rule`, `estimated_amount`, `limit` |
| `DUPLICATE_NOTIFICATION` | `rule`, `claim_reference` of the existing recorded notification (WI-0151, AC-2) |
| `POLICY_MASTER_TIMEOUT` | `policy_number`, `reason` (`timeout`) |
| `POLICY_MASTER_UNREACHABLE` | `policy_number`, `reason` (`unreachable`) |
| `POLICY_MASTER_UNPARSABLE` | `policy_number`, `reason` (`unparsable`) |

### Worked examples

These three are different failure classes. Their `detail` objects are
not the same shape and cannot be produced by one handling path.

**Rule failure.** The body was interpreted. V-2 failed. `detail` names
the rule and the two dates the comparison used.

```
{
  "code": "LOSS_BEFORE_INCEPTION",
  "message": "Loss date precedes policy inception.",
  "detail": {
    "rule": "V-2",
    "loss_date": "2026-02-11",
    "effective_date": "2026-03-01"
  }
}
```

**Request the service could not interpret.** No rule ran. `detail` has
no `rule`. It names the field that was not well formed.

```
{
  "code": "MALFORMED_REQUEST",
  "message": "The request body could not be interpreted.",
  "detail": {
    "field": "estimated_amount"
  }
}
```

**Policy master that did not answer.** The caller did nothing wrong. No
rule ran. `detail` has no `rule`. It names the policy that was looked
up and why the master produced no usable answer.

```
{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not answer in time.",
  "detail": {
    "policy_number": "MOT-4471",
    "reason": "timeout"
  }
}
```

## 6. Status code mapping

Every `code` this contract defines maps to exactly one status. A
recorded notification has no error `code` and returns 201.

The policy master boundary is four conditions, not one. The master
answering that there is no such policy is the caller's data (V-1,
4xx). The master timing out, being unreachable, or returning something
the service cannot parse are facts about the dependency (5xx). The
three 5xx codes are not interchangeable: timeout, unreachability, and
an unusable response require different action from the caller.

| Code | Status | When |
| --- | --- | --- |
| — | 201 | Section 3. The notification was recorded. |
| `MALFORMED_REQUEST` | 400 | Section 2.4. The body cannot be interpreted. |
| `DUPLICATE_NOTIFICATION` | 409 | V-6 |
| `POLICY_NOT_FOUND` | 422 | V-1. The policy master answered: no such policy. |
| `LOSS_BEFORE_INCEPTION` | 422 | V-2 |
| `POLICY_CANCELLED` | 422 | V-7 |
| `LOSS_AFTER_EXPIRY` | 422 | V-3 |
| `TYPE_NOT_COVERED` | 422 | V-5 |
| `AMOUNT_EXCEEDS_LIMIT` | 422 | V-4 |
| `POLICY_MASTER_UNREACHABLE` | 503 | The policy master could not be reached. |
| `POLICY_MASTER_UNPARSABLE` | 502 | The policy master responded; the response could not be used. |
| `POLICY_MASTER_TIMEOUT` | 504 | The policy master did not answer in time. |
