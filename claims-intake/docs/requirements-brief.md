# Requirements Brief: Claims Intake Service

Open work items raised against the claims intake service. Each carries an origin, the authority it rests on, and acceptance criteria that are binary.

An item is converted when the behavior it describes appears in `docs/api-contract.md` as a specified rule, is covered by a test named for the criterion it protects, and is implemented by a commit that references the item.

```
WI-0142  Reject notifications with a loss date before policy inception

Origin:    Defect raised by claims operations, 2026-03-04
Authority: Product rule PR-11, "Cover attaches at inception"

Currently a notification whose loss_date precedes the policy
effective_date is accepted and creates a claim record. Operations
then cancels it by hand. Three occurrences last month.

AC-1  A notification whose loss_date is earlier than the policy
      effective_date is rejected and no claim record is created.
AC-2  The rejection returns HTTP 422 with error code
      LOSS_BEFORE_INCEPTION in the standard error envelope.
AC-3  A notification whose loss_date equals the policy
      effective_date is accepted. Cover attaches on the day.
AC-4  A notification whose policy_number is not found is rejected
      with POLICY_NOT_FOUND and is not evaluated against AC-1.

Contract: docs/api-contract.md, section 4.2
Status:   Converted. Rule V-2.
```

```
WI-0151  Reject duplicate notifications

Origin:    Defect raised by claims operations, 2026-03-19
Authority: Operations procedure OP-4, "One claim per loss event"

A claims handler who submits the same notification twice, which
happens when the portal times out and they retry, creates two claim
records for one loss. Operations then merges them by hand.

AC-1  A notification whose policy_number, loss_date, and claim_type
      all match an existing recorded notification is rejected and no
      second claim record is created.
AC-2  The rejection returns HTTP 409 with error code
      DUPLICATE_NOTIFICATION and includes the claim reference of the
      existing record in the detail object.
AC-3  A notification matching a previous submission that was rejected
      is not a duplicate. Nothing was recorded, so there is nothing
      to duplicate.

Contract: docs/api-contract.md, section 4.2
Status:   Open.
```

```
WI-0158  Reject notifications against cancelled policies

Origin:    Raised by underwriting, 2026-03-22
Authority: Product rule PR-19, "Cancellation ends cover"

A policy that is cancelled mid-term keeps its original expiry_date
in the policy master. Cover has ended, but the intake service still
accepts notifications against it because the loss date falls inside
the original term.

AC-1  Where a policy has a cancellation_date, a notification whose
      loss_date falls on or after that date is rejected with error
      code POLICY_CANCELLED.
AC-2  Cancellation takes effect at the start of the cancellation
      date. A loss on the cancellation date itself is not covered.
AC-3  Where cancellation_date is null the policy was not cancelled
      and this rule does not apply.
AC-4  Where a policy is cancelled and the loss also falls outside
      the original term, the handler must be told the policy was
      cancelled. Reporting only that the loss is after expiry sends
      them to the wrong system to investigate.

Contract: docs/api-contract.md, section 4.2
Status:   Open.
```
