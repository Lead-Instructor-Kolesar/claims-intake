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

### 4.1 Evaluation order

Rules are evaluated in the order they appear in the table in section
4.2. The identifier is a label for reference and does not indicate
evaluation order. V-1 short circuits: if it fails, no rule that reads
a policy field is evaluated.

When a notification violates more than one rule, only the first
failing rule in table order is reported. The caller receives that
rule's code and status, not a list of all violations, and should not
assume no other rule was also broken.

A `claim_type` value not in the section 2.3 vocabulary is refused
with status 400 before any rule in this table is evaluated.

An `estimated_amount` value carrying more than two decimal places is
refused with status 400 before any rule in this table is evaluated.

A `policy_number` that is empty is refused with status 400 before any
rule in this table is evaluated.

An `estimated_amount` that is not greater than zero is refused with
status 400 before any rule in this table is evaluated.

### 4.2 Rule table

| ID  | Condition                                      | Code                     | Status |
| --- | ----------------------------------------------- | ------------------------ | ------ |
| V-1 | `policy_number` exists in the policy master (exact, case-sensitive match against the value as stored)    | `POLICY_NOT_FOUND`       | 422    |
| V-7 | `loss_date` < policy `cancellation_date` (when `cancellation_date` is not null) | `POLICY_CANCELLED` | 422 |
| V-2 | `loss_date` >= policy `effective_date`          | `LOSS_BEFORE_INCEPTION`  | 422    |
| V-3 | `loss_date` <= policy `expiry_date`             | `LOSS_AFTER_EXPIRY`      | 422    |
| V-4 | `estimated_amount` <= policy `limit`            | `AMOUNT_EXCEEDS_LIMIT`   | 422    |
| V-5 | `claim_type` permitted on the policy's product  | `TYPE_NOT_COVERED`       | 422    |
| V-6 | no matching recorded notification exists (`policy_number`, `loss_date`, and `claim_type`) | `DUPLICATE_NOTIFICATION` | 409 |

Boundaries are inclusive as written. A loss on the inception date is
covered (WI-0142, AC-3). An amount equal to the limit is within cover.

## 5. Error envelope

Every non-2xx response returns this shape and no other:

{
  "code": "string",
  "message": "string",
  "detail": {}
}

`code` is a stable, machine-readable identifier. Callers branch on
`code`, and its meaning does not change once published. Adding a new
code is a compatible change; redefining what an existing code means
is not.

`message` is a human-readable description for display. It may be
reworded at any time without notice. Callers must not parse or branch
on `message`.

`detail` carries the values relevant to the specific failure. Its
keys vary by code and are not fixed by this contract as a whole.
Callers may rely on `detail` being present and being an object. Callers
must not assume any particular key exists inside `detail` for a code
they have not specifically read this contract for, and must not build
logic that breaks if `detail`'s keys change for a code they have not
read.

### 5.1 Worked examples

**A rule failure** (`422`, from the rule table):

{
  "code": "LOSS_BEFORE_INCEPTION",
  "message": "Loss date precedes policy inception.",
  "detail": {
    "rule": "V-2",
    "loss_date": "2026-02-11",
    "effective_date": "2026-03-01"
  }
}

**An uninterpretable request** (`400`, section 2.4):

{
  "code": "MALFORMED_REQUEST",
  "message": "Request body could not be interpreted.",
  "detail": {
    "field": "estimated_amount",
    "reason": "expected decimal, received string"
  }
}

**A policy master failure** (`503`, section 6):

{
  "code": "POLICY_MASTER_UNAVAILABLE",
  "message": "Policy master could not be reached.",
  "detail": {
    "dependency": "policy-master",
    "attempted_at": "2026-08-18T14:02:11Z"
  }
}


## 6. Status code mapping

| Code                             | Status | Cause                                                   |
|-----------------------------------|--------|------------------------------------------------------- |
| `MALFORMED_REQUEST`               | 400    | Request body could not be interpreted (sections 2.4 and 4.1) |
| `POLICY_NOT_FOUND`                | 422    | V-1: policy master answered, no match                  |
| `POLICY_CANCELLED`                | 422    | V-7                                                    |
| `LOSS_BEFORE_INCEPTION`           | 422    | V-2                                                    |
| `LOSS_AFTER_EXPIRY`               | 422    | V-3                                                    |
| `AMOUNT_EXCEEDS_LIMIT`            | 422    | V-4                                                    |
| `TYPE_NOT_COVERED`                | 422    | V-5                                                    |
| `DUPLICATE_NOTIFICATION`          | 409    | V-6                                                    |
| `POLICY_MASTER_UNAVAILABLE`       | 503    | Policy master unreachable                              |
| `POLICY_MASTER_TIMEOUT`           | 504    | Policy master did not respond in time                  |
| `POLICY_MASTER_INVALID_RESPONSE`  | 502    | Policy master response could not be parsed             |

Every code the service can produce appears above exactly once. No
two codes share a meaning: `POLICY_NOT_FOUND` is the only code for a
policy that does not exist, and it is not duplicated under a different
name elsewhere in this table.
