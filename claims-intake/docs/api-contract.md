# Claims Intake Service: API Contract

Version 0.6. Owned by the claims intake team. Consumed by the claims portal team.

Version 0.5 completed sections 4, 5 and 6, added rules `V-6` and `V-7` (WI-0151 and
WI-0158), replaced the ascending-identifier evaluation order of 0.4 with the staged order
in 4.1, and recorded three determinations in 4.4. This is component C1 of the week's lab
and is what Days 2, 3 and 4 are built against.

Version 0.6 adds one code, `NOT_FOUND` (404), to section 6.4 and adds 404 to the status
set in 6.5. Adding a code is a compatible change under section 1. It was added because
section 5.1 requires every response that is not `201 Created` to carry the error
envelope, and a request to a path this service does not define is such a response. Before
this version the contract described no code for it, so the service could either answer
outside the envelope or invent a code the document did not list. Recorded in the Day 4
reconciliation note in `docs/payload-triage.md`.

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

Validation runs in ordered stages. A stage is entered only if every rule in every
preceding stage passed. Within a stage, rules are evaluated in ascending identifier
order. Evaluation stops at the first rule whose condition does not hold, and that
rule's code is the one returned.

| Stage | The question the stage answers                                          | Rules      |
| ----- | ---------------------------------------------------------------------- | ---------- |
| 0     | Can this request be interpreted at all?                                | `V-0`      |
| 1     | Does the policy exist, and could the policy master be read?            | `V-1`      |
| 2     | Is there cover in force to notify against?                             | `V-7`      |
| 3     | Does the loss fall inside the term the policy was written for?          | `V-2`, `V-3` |
| 4     | Is the content of this notification admissible on this policy?          | `V-4`, `V-5` |
| 5     | Has this loss already been recorded?                                   | `V-6`      |

**Transport precedes stage 0.** The conditions in section 6.4 — a method other than
`POST`, a `Content-Type` that is not `application/json`, a path this contract does
not define — are decided before stage 0 is entered, because they determine whether
there is a JSON body to interpret at all. They are not rules and carry no `V-n`
identifier. Where a request fails both a transport check and a stage 0 check, the
transport code is returned and the body is never parsed.

**Identifiers are labels, not an order.** `V-n` is a permanent name for a rule,
allocated in the order rules were written into this contract. It carries no
information about when the rule is evaluated. Version 0.4 of this document said
rules are evaluated in ascending identifier order; that statement was true only
while the rules happened to have been written in stage order, and adding `V-7`
broke it (see "This is what resolves WI-0158 AC-4" below). The stage table above is
now the only
statement of evaluation order this contract makes. A rule added in a future version
takes its place by the stage it belongs to and not by its number, so a later
addition cannot reopen this question.

**Why the stages are in this order.** Each stage presupposes the answer to the one
before it. Stage 0 precedes everything because a value that could not be interpreted
cannot be compared against anything. Stage 1 precedes every stage that reads a policy
field, because if there is no policy there is nothing to compare against, and
reporting `LOSS_BEFORE_INCEPTION` for a policy number the master does not hold is a
false statement about the client's data (WI-0142, AC-4). Stage 2 precedes stage 3
because whether cover exists is a prior question to how long it was written to run.
Stage 3 precedes stage 4 because the limit and the permitted claim types are terms of
a contract of insurance, and they are only worth testing a loss against once the loss
is known to fall inside the period that contract covered. Stage 5 is last because the
duplicate check is a question about what has already been recorded, and a notification
the service would refuse anyway would never have been recorded; telling a caller they
already hold a claim for a loss the service would not accept states something that is
not true of the payload in front of it.

**This is what resolves WI-0158 AC-4.** A policy that is cancelled and whose loss also
falls after the original `expiry_date` violates `V-7` and `V-3` together. `V-7` is in
stage 2 and `V-3` is in stage 3, so the caller receives `POLICY_CANCELLED` and never
`LOSS_AFTER_EXPIRY`. The handler is told cover was ended, which is the fact that sends
them to the right system, rather than that the loss was late against a term the policy
never ran to its end. The general form of the rule is that where two rules are both
violated, the caller is told the one that names the more fundamental fact about the
policy, and the stage table is the ranking.

**Assigning a future rule to a stage.** Ask what the caller does with the answer. A
rule that says the request could not be read is stage 0. A rule about the identity or
readability of the policy record is stage 1. A rule that says cover does not exist for
this loss whatever its date is stage 2. A rule that compares `loss_date` against a date
on the policy is stage 3. A rule that compares any other request field against a term
of the policy is stage 4. A rule that queries what the service has already recorded is
stage 5.

**When more than one rule is violated.** The caller receives exactly one refusal: one
`code`, one HTTP status, one `detail` object. The service does not accumulate failures
and the error envelope in section 5 has no field that reports a second one. Which
refusal is returned is fully determined by the stage table plus ascending identifier
order inside a stage, so it is not "whichever the implementation happened to check
first": two conforming implementations return the same code for the same payload
against the same policy master and repository state.

There is one deliberate exception, and it is inside a single rule rather than across
rules. `V-0` reports every interpretation violation it finds in one response, as a list
in `detail.violations` (section 4.3). All of them are defects in one piece of caller
code, and a developer should not have to submit five times to be told about five
mistakes. Once `V-0` passes, one refusal means one rule, without exception.

**A refusal names one rule. It does not clear the others.** A caller must not infer from
an `AMOUNT_EXCEEDS_LIMIT` refusal that the claim type was permitted, or from a
`POLICY_CANCELLED` refusal that anything else about the notification was acceptable. A
corrected resubmission may be refused again under a later rule. Nothing in this
contract promises that a refusal is the only thing wrong with a payload.

### 4.2 Rule table

Each condition below is what must hold. Where it does not hold, the notification is
refused with the code shown and nothing is recorded.

| ID  | Condition                                                                                                                                                                              | Code                     | Status |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ | ------ |
| V-1 | `policy_number` exists in the policy master                                                                                                                                            | `POLICY_NOT_FOUND`       | 422    |
| V-2 | `loss_date` >= policy `effective_date`                                                                                                                                                 | `LOSS_BEFORE_INCEPTION`  | 422    |
| V-3 | `loss_date` <= policy `expiry_date`                                                                                                                                                    | `LOSS_AFTER_EXPIRY`      | 422    |
| V-4 | `estimated_amount` <= policy `limit`                                                                                                                                                   | `AMOUNT_EXCEEDS_LIMIT`   | 422    |
| V-5 | `claim_type` is a member of policy `permitted_claim_types`                                                                                                                                         | `TYPE_NOT_COVERED`       | 422    |
| V-6 | no recorded notification `R` exists for which `R.policy_number == policy_number` and `R.loss_date == loss_date` and `R.claim_type == claim_type`                                        | `DUPLICATE_NOTIFICATION` | 409    |
| V-7 | policy `cancellation_date` is `null`, or `loss_date` < policy `cancellation_date`                                                                                                       | `POLICY_CANCELLED`       | 422    |

**Boundaries.**

`V-2`, `V-3` and `V-4` are inclusive as written. A loss on the `effective_date` is
covered (WI-0142, AC-3). A loss on the `expiry_date` is covered. An amount exactly
equal to the `limit` is within cover.

`V-7` is strict on the comparison and the strictness is the point. The comparison is
`loss_date < cancellation_date`, so a loss on the `cancellation_date` itself fails the
rule and is refused. Cancellation takes effect at the start of the cancellation date
(WI-0158, AC-2), which means the last day of cover on a cancelled policy is
`cancellation_date - 1 day`. Restated so that neither reading survives: `loss_date`
earlier than `cancellation_date` passes; `loss_date` equal to `cancellation_date`
fails; `loss_date` later than `cancellation_date` fails.

`V-7` does not apply where `cancellation_date` is `null` (WI-0158, AC-3). `null` is the
only representation of "not cancelled"; the field is present on every policy record, so
an absent `cancellation_date` is a policy master defect and is handled as
`POLICY_MASTER_INVALID_RESPONSE` (section 6.3), not as an uncancelled policy.

`V-7` reads only `cancellation_date`. It does not read `expiry_date`. A cancelled policy
is refused under `V-7` whether the loss falls inside the original term or outside it,
which is what stage 2 preceding stage 3 delivers.

`V-6` compares on exactly three fields and on nothing else (WI-0151, AC-1).
`estimated_amount` and `description` are not part of the match, so a resubmission that
differs only in amount is still a duplicate. The comparison is against recorded
notifications only. A submission that was refused was never written (section 3), so
there is nothing for a later submission to duplicate (WI-0151, AC-3), and no refusal
this contract defines can ever cause a subsequent `DUPLICATE_NOTIFICATION`. The
`claim_reference` of the existing record is returned in `detail` (WI-0151, AC-2, and
section 5.3).

**Dates and amounts are compared as values, not as text.** `loss_date`,
`effective_date`, `expiry_date` and `cancellation_date` are compared as calendar
dates. `estimated_amount` and `limit` are compared as exact decimal values, so
`5000.00` and `5000` denote the same amount and no comparison depends on how a value
was written. In `V-6`, `loss_date` is matched as a calendar date and `policy_number`
and `claim_type` are matched as exact strings.

**`policy_number` is compared exactly.** `V-1` looks the value up in the policy master
as sent, byte for byte and case sensitively. The service does not upper-case, trim,
strip punctuation, or otherwise normalise `policy_number` before lookup, and `V-6`
matches on the same unnormalised value. `mot-4471` and `MOT-4471` are therefore
different identifiers, and a request carrying the first against a master that holds the
second is refused under `V-1`. This is determination **D-1** in section 4.4.

### 4.3 Stage 0: request interpretation (`V-0`)

`V-0` is the gate section 2.4 describes. It is a single rule because it answers a single
question — can this request be interpreted — and it is numbered `V-0` so that the
triage and the tests have an identifier to name. It is not a business rule and it reads
no policy field, which is why it is stated here rather than in the table in 4.2.

`V-0` produces one of two codes, both with status 400:

| Condition                                                                     | Code              | Status |
| ----------------------------------------------------------------------------- | ----------------- | ------ |
| The request body is not valid JSON, or is not a JSON object                    | `MALFORMED_JSON`  | 400    |
| The body parsed as JSON but does not satisfy every constraint listed below     | `SCHEMA_INVALID`  | 400    |

The two are separate codes because they differ in what the service can tell the caller.
`MALFORMED_JSON` cannot name a field, since nothing could be located inside the body;
`SCHEMA_INVALID` names every field that failed and how. A caller's developer acts on
the two differently: the first is a serialisation or transport defect, the second is a
field-level defect they can go and read.

A request fails `V-0` with `SCHEMA_INVALID` where any of the following holds:

1. A field required by section 2.2 is absent, or is present with the value `null`
   (`policy_number`, `loss_date`, `claim_type`, `estimated_amount`).
2. A field carries a value of the wrong JSON type, as fixed in the paragraph below.
3. A field is present that section 2.2 does not define (section 2.2, final paragraph).
4. `policy_number` is the empty string or contains only whitespace.
5. `loss_date` is not of the form `YYYY-MM-DD`, or is of that form but is not a real
   calendar date (`2026-02-30`).
6. `claim_type` is a string that is not one of the five values in section 2.3. This is
   determination **D-2** in section 4.4.
7. `estimated_amount` carries more than two decimal places. This is determination
   **D-3** in section 4.4.
8. `estimated_amount` is zero or negative (section 2.2: greater than zero).

`description` is optional. Absent and `null` are equivalent and neither is a violation.

**How the section 2.2 types are carried in JSON.** Violation 2 tests the JSON type of
each field, so the mapping from the section 2.2 type column onto a JSON type has to be
fixed here or two implementations will disagree about every payload. `policy_number`,
`loss_date`, `claim_type` and `description` are JSON strings. `estimated_amount` is the
`decimal` of section 2.2, and JSON has no decimal primitive: it is carried as a JSON
**string** holding a decimal numeral, which is how every fixture in `data/` and the
`limit` field of the policy master represent money. A JSON number is the wrong type and
fails violation 2, because a number is read as a binary float while `estimated_amount`
is the operand `V-4` compares against `limit` and both operands must be exact. A string
that is not a decimal numeral — one not matching `-?[0-9]+(\.[0-9]+)?` — fails
violation 2. A string that is a decimal numeral but carries more than two decimal
places is the case violation 7 names; it is violation 7 and not violation 2 because the
service could read the value and is refusing its scale, which is what determination D-3
settles.

Every violation found in one request is reported together, in `detail.violations`
(section 5.4, example 2). No stage 1 rule runs, no policy is read, and nothing is
recorded.

### 4.4 Determinations this version makes

Three questions were left undetermined by version 0.4. They are settled here so that a
reader of this contract alone cannot arrive at the other reading. Each is recorded with
its rationale in `docs/payload-triage.md`.

**D-1. `policy_number` is matched exactly, including case.** Section 2.2 says the value
is the "identifier as held in the policy master", which is a requirement on the caller
to send it as held, not an instruction to the service to work out what was meant. The
service does not own policy identity; section 1 states the policy master is a dependency
this service reads and does not write. Normalising case would additionally have to be
applied to the `V-6` duplicate key, or `MOT-4471` and `mot-4471` would record two claims
for one loss and break WI-0151 AC-1. A lower-case policy number reaches the master
unchanged, the master reports no match, and the caller receives `POLICY_NOT_FOUND` (422).

**D-2. A `claim_type` outside the section 2.3 vocabulary fails `V-0`, not `V-5`.** The
vocabulary is fixed by this contract (section 2.3), so a value outside it is a request
this contract does not define, in the same class as a misspelled field name. `V-5` asks
a different question: whether a claim type the contract does define is permitted on the
product this policy is written on, which is "a property of the policy record" (section
2.3). `TYPE_NOT_COVERED` is therefore reserved for a value inside the vocabulary, and
`flood` is refused with `SCHEMA_INVALID` (400) without a policy being read.

**D-3. `estimated_amount` must carry no more than two decimal places, and the service
does not round.** Section 2.2 states the scale as part of the type. A value of
`3499.999` is refused with `SCHEMA_INVALID` (400). Rounding it would record a monetary
value the caller did not send, which is the reasoning section 2.2 already gives for
refusing a body that carries an undefined field rather than ignoring it, and the
rounding direction would itself be unspecified, so two conforming implementations could
record different amounts for the same payload.

## 5. Error envelope

### 5.1 Shape

Every response this service produces that is not `201 Created` carries this body, with
`Content-Type: application/json`:

```json
{
  "code": "LOSS_AFTER_EXPIRY",
  "message": "Loss date 2026-04-02 is after the policy expiry date 2026-02-28.",
  "detail": {
    "policy_number": "MOT-4489",
    "loss_date": "2026-04-02",
    "expiry_date": "2026-02-28"
  }
}
```

All three keys are present on every error response. `code` and `message` are always
non-empty strings. `detail` is always a JSON object and may be empty. There is no
`status` field in the body: the status is in the HTTP status line and in one place only,
so the two cannot disagree.

### 5.2 What is a promise and what is not

| Part of the response                          | Stable?                         | What a caller may do with it                               |
| --------------------------------------------- | ------------------------------- | ---------------------------------------------------------- |
| HTTP status                                   | Yes, one per code (section 6)   | Branch on it; assert on it in tests                        |
| `code`                                        | Yes                             | Branch on it; assert on it; log it; use it as a metric label |
| `message`                                     | **No**                          | Log it; show it to a person. Nothing else                    |
| `detail` is present and is an object          | Yes                             | Read it after branching on `code`                          |
| The keys of `detail` for a given `code`       | Yes, and additive               | Read the keys this contract lists for that code            |
| The keys of `detail` across codes             | **No**                          | Nothing                                                    |

**`code` is the stable promise.** The set of codes is enumerated in section 6. A code
never changes meaning and never changes status without a version increment agreed with
the portal team (section 1). New codes may be added in a compatible change, so a caller
must have a default branch for a code it does not recognise, and that branch must not
assume anything about `detail`.

**`message` is not a promise.** It is English prose for a human reader. Its wording,
length, punctuation and the values interpolated into it may change in any release,
without a version increment and without notice. It may be localised. A caller that
matches on `message`, parses values out of it, or asserts on it in a test has built on
something this contract does not maintain, and it will break. Everything a caller needs
to make a decision is in `code`, the status, and the documented keys of `detail`.

What follows for a caller: two responses with the same `code` and different `message`
are the same outcome and must be handled identically. Two responses with the same
`message` and different `code` are different outcomes and must not be.

### 5.3 What may be relied on inside `detail`

`detail` is scoped to `code`. Its keys carry the values the decision was made on, and
because different codes are decided on different things, the keys differ by code. There
is no key that appears under every code.

A caller may rely on:

- `detail` being present and being a JSON object on every error response.
- For a `code` this contract documents, the keys listed for that code in sections 6.2,
  6.3 and 6.4 being present, with the types listed.
- New keys being added to a code's `detail` over time. This is a compatible change and
  a caller must ignore keys it does not recognise (section 1).

A caller may not rely on:

- Any key being present without first branching on `code`. Reading
  `detail.policy_number` before checking `code` is a defect: `MALFORMED_JSON` never
  carries it, and section 1 permits new codes whose `detail` has no policy fields.
- A key carrying the same meaning under two codes. `reason` under
  `POLICY_MASTER_TIMEOUT` describes our dependency; it is not the reason a rule failed.
- `detail` being a flat map of scalars. Under `SCHEMA_INVALID` it contains an array of
  objects.
- `detail` being non-empty, or on the count, order or absence of keys.
- `detail` being suitable to display to a person unaltered. It is structured data for
  the caller's code; `message` is the text for a person.

One consequence worth stating because a caller could get it wrong in a costly way:
`claim_reference` appears in the `detail` of exactly one refusal, `DUPLICATE_NOTIFICATION`,
and it is the reference of a notification recorded earlier (WI-0151, AC-2). It is not a
reference for the submission being refused. No reference is ever issued for a refused
notification (section 3).

### 5.4 Three worked examples

These are three different classes of failure, not three instances of one. The table in
5.5 states what separates them.

**Example 1. A rule failed.** `V-3`, a loss after the expiry date. The request was
understood, the policy was read, and a named comparison against a policy field did not
hold. `detail` carries the operands of that comparison, so that a claims handler reading
the refusal can see the two dates that decided it.

```
422 Unprocessable Entity

{
  "code": "LOSS_AFTER_EXPIRY",
  "message": "Loss date 2026-04-02 is after the policy expiry date 2026-02-28.",
  "detail": {
    "policy_number": "MOT-4489",
    "loss_date": "2026-04-02",
    "expiry_date": "2026-02-28"
  }
}
```

**Example 2. The request could not be interpreted.** `V-0`. No policy was read, so
`detail` cannot name a single policy field. What it names instead is locations in the
request, and there are as many as the request contains, so the shape is an array rather
than a flat map (section 4.1, the `V-0` exception).

```
400 Bad Request

{
  "code": "SCHEMA_INVALID",
  "message": "The request could not be interpreted. 3 fields are invalid.",
  "detail": {
    "violations": [
      { "field": "estimated_amount", "problem": "required field absent" },
      { "field": "claim_type", "problem": "value 'flood' is not one of: collision, theft, glass, liability, weather" },
      { "field": "policy_holder_name", "problem": "field is not defined by this contract" }
    ]
  }
}
```

**Example 3. The policy master did not answer.** Nothing in the request is wrong and
nothing about any policy is known, so `detail` contains no caller data at all. What it
carries is operational: which dependency, whether a retry is worth attempting, and the
identifier that lets our operations team find this attempt in the logs.

```
504 Gateway Timeout

{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond in time. Please retry.",
  "detail": {
    "dependency": "policy_master",
    "reason": "timeout",
    "retryable": true,
    "correlation_id": "01HB3K9QW7ZN4T"
  }
}
```

### 5.5 What separates the three

|                                        | Example 1 (`V-3`)       | Example 2 (`V-0`)          | Example 3 (dependency)       |
| -------------------------------------- | ----------------------- | -------------------------- | ---------------------------- |
| Whose fault                             | The caller's data       | The caller's code          | Ours                         |
| Who should see it                       | The claims handler      | A developer, via logs      | Operations, via alerting     |
| Shape of `detail`                       | Flat map: the operands of one comparison | Object holding an array, one entry per violation | Operational facts, no caller data |
| Number of faults reported               | Exactly one             | All of them                | Not applicable               |
| Is retrying the identical payload useful | No, the answer is fixed | No, the code must change   | Yes, with backoff            |
| Was anything recorded                   | No                      | No                         | No                           |

A caller that handles all three with one branch is wrong in three ways: it shows a
developer's defect to a claims handler, it retries a refusal that will never change, and
it fails to retry the one failure that would have succeeded.

## 6. Status code mapping

Every outcome the service can produce appears in this section. A code maps to exactly
one status, and no status is reached by two codes that mean the same thing.

### 6.1 Success

| Outcome                                                | Status |
| ------------------------------------------------------ | ------ |
| Every rule in section 4 passed; the notification is recorded | 201    |

### 6.2 Request interpretation and rule failures

| Code                     | Status | Decided by | Keys in `detail`                                                     |
| ------------------------ | ------ | ---------- | -------------------------------------------------------------------- |
| `MALFORMED_JSON`         | 400    | `V-0`      | none (`{}`)                                                          |
| `SCHEMA_INVALID`         | 400    | `V-0`      | `violations` (array of `{ field, problem }`)                          |
| `POLICY_NOT_FOUND`       | 422    | `V-1`      | `policy_number`                                                      |
| `LOSS_BEFORE_INCEPTION`  | 422    | `V-2`      | `policy_number`, `loss_date`, `effective_date`                       |
| `LOSS_AFTER_EXPIRY`      | 422    | `V-3`      | `policy_number`, `loss_date`, `expiry_date`                          |
| `AMOUNT_EXCEEDS_LIMIT`   | 422    | `V-4`      | `policy_number`, `estimated_amount`, `limit`                         |
| `TYPE_NOT_COVERED`       | 422    | `V-5`      | `policy_number`, `claim_type`, `permitted_claim_types`, `product`    |
| `DUPLICATE_NOTIFICATION` | 409    | `V-6`      | `policy_number`, `loss_date`, `claim_type`, `claim_reference`        |
| `POLICY_CANCELLED`       | 422    | `V-7`      | `policy_number`, `loss_date`, `cancellation_date`                    |

The 400 codes are the section 2.4 case of a request that could not be interpreted. The
422 codes are the section 2.4 case of a request that was interpreted and whose content
is not admissible. `DUPLICATE_NOTIFICATION` is 409 rather than 422 because the request
is admissible and the obstacle is the state of our records, not the content of the
payload (WI-0151, AC-2). 409 is used by this code alone.

Two codes share 400 and six share 422. In each case the codes mean different things and
require different action: `MALFORMED_JSON` and `SCHEMA_INVALID` differ in whether the
service could locate the fault; each 422 code names a different comparison against a
different policy field and sends the handler to a different remedy.

### 6.3 The policy master boundary

Four conditions arise at the dependency. Section 1 requires that a policy that cannot
be read and a policy that does not exist are specified separately, because they demand
different action.

| Condition at the policy master                          | Code                             | Status |
| ------------------------------------------------------- | -------------------------------- | ------ |
| Answered, and holds no policy with that number           | `POLICY_NOT_FOUND`               | 422    |
| Did not answer within the service's timeout              | `POLICY_MASTER_TIMEOUT`          | 504    |
| Could not be reached at all                              | `POLICY_MASTER_UNAVAILABLE`      | 503    |
| Answered with something the service cannot parse         | `POLICY_MASTER_INVALID_RESPONSE` | 502    |

The first is a fact about the caller's data, so it is 4xx and it is the same code as
`V-1`; it is not given a second code, because "the master answered and holds no such
policy" and "`V-1` failed" are the same condition, and two codes for one condition would
force the portal to handle it twice.

The other three are facts about our systems. The caller sent a valid request and can do
nothing about any of them, so they are 5xx: returning 4xx would tell a claims handler to
correct a payload that is not wrong. They are three codes and not one because the
operational response differs. A timeout means the dependency is reachable and slow, so a
retry with backoff is likely to succeed. Unreachable means a network or deployment fault,
so an immediate retry is not worth making. An unparsable response means the policy master
has broken its own contract, so retrying will not help and it must be escalated rather
than absorbed. Collapsing them would discard exactly the distinction that decides what
happens next.

On all three, nothing was recorded, and `detail` carries
`dependency`, `reason`, `retryable` and `correlation_id`. `reason` takes the values
`timeout`, `unreachable` and `unparsable`. `retryable` is `true` under
`POLICY_MASTER_TIMEOUT` and `POLICY_MASTER_UNAVAILABLE`, and `false` under
`POLICY_MASTER_INVALID_RESPONSE`.

A retry of the identical payload after any 5xx is safe. If the original attempt did in
fact record the notification, the retry is refused by `V-6` with the existing
`claim_reference`, which is the correct outcome and is the retry case WI-0151 was raised
about.

### 6.4 Transport and service-level failures

These are decided before stage 0 (section 4.1) or, for `INTERNAL_ERROR`, at any point.
They are not rules and carry no `V-n` identifier, but they are failures the service can
produce, so they carry the section 5.1 envelope and are enumerated here.

| Condition                                        | Code                     | Status | Keys in `detail`            |
| ------------------------------------------------ | ------------------------ | ------ | --------------------------- |
| `Content-Type` is not `application/json`         | `UNSUPPORTED_MEDIA_TYPE` | 415    | `received`, `expected`      |
| A method other than `POST` on `/notifications`   | `METHOD_NOT_ALLOWED`     | 405    | `method`, `allowed` (array) |
| A request to a path this contract does not define | `NOT_FOUND`              | 404    | none (`{}`)                 |
| Any unhandled fault inside this service          | `INTERNAL_ERROR`         | 500    | `correlation_id`            |

A `405` response also carries the HTTP `Allow` header, as the method requires.

Under `UNSUPPORTED_MEDIA_TYPE`, `received` is the `Content-Type` as sent, and is
`null` where the request carried no `Content-Type` at all. A caller reading it must
therefore accept a string or `null`, which is why it is reported rather than used as
anything a caller branches on.

`NOT_FOUND` carries an empty `detail`. It is a statement about the request line and
not about any policy or payload, so there is nothing about the caller's data to
report. It is distinct from `POLICY_NOT_FOUND`, which is a fact about a policy the
master does not hold and is 422; a caller must not collapse the two, because one
means the portal called the wrong URL and the other means a claims handler typed a
policy number that does not exist.

`INTERNAL_ERROR` is the only code that does not correspond to a condition this contract
describes, and that is its purpose: it exists so that no failure escapes the envelope.
Its `detail` carries `correlation_id` and nothing else, because a fault we did not
anticipate is a fault we cannot describe safely to a caller. It is 500 and never 4xx,
and a caller may retry.

### 6.5 Complete status set

`201`, `400`, `404`, `405`, `409`, `415`, `422`, `500`, `502`, `503`, `504`. A status
outside this set is a defect in the service.

Invariants a caller may hold to:

- Exactly one status per code, as listed above.
- Every response other than 201 carries the section 5.1 envelope.
- No refusal and no failure of any kind records a notification or issues a claim
  reference (section 3).
- Every 4xx except 409 is deterministic: the identical payload against the same policy
  master state returns the identical code. Retrying it is pointless.
- Every 5xx is possibly transient. Retrying the identical payload is safe.
