Things to do:
1. Implement request model (NotificationRequest). Parses payload/ rejects anything structurally unacceptable (422). 
    - Every field carries the type that makes the downstream comparison correct, extra fields are forbidden, and no field carries a default that invents data the caller did not send. 
    - The Day 2 articles show the shape. Your job is to make every choice in it follow from your contract rather than from the example.

2. Implement the policy model. Policy represents what the policy master returns, including cancellation_data, whose type must take WI-0158.
    - WI-0158: ```
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
3. Implement the supporting value types. RuleFailure carries a rule identifier and an error code and is immutable. It exists so that a rule identifier can never be passed where an error code is expected. ClaimRecord represents a recorded notification and carries its claim reference.

4. Implement the repository. It stores accepted notifications and returns a claim reference for each. The reference matches the format your contract's success response specifies and is unique across all records. Two behaviors are load bearing and both come from WI-0151. The repository can tell you whether a notification duplicates an existing record, matching on policy_number, loss_date, and claim_type together. And a notification that was rejected is not recorded at all, so it can never be the thing a later submission duplicates.

WI-0151:

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

5. Write the model tests. tests/unit/test_models.py. Cover what the model accepts and what it refuses, using parametrization with named cases rather than one test per input or a loop inside one test. Every field constraint you declared gets a case that violates it. The payloads in data/fnol_invalid.json and data/fnol_edge.json are your source of realistic inputs, and you should be able to state for each one whether it fails at the model or survives to the rules.

6. Write the repository tests. tests/unit/test_repository.py. Cover recording, reference uniqueness, duplicate detection including the case where only two of the three matching fields agree, and the WI-0151 AC-3 behavior that a rejected notification leaves nothing to duplicate. Fixtures build fresh objects. No test may depend on another test having run.

7. Run the tools and fix what they find. ruff check and mypy both exit clean. A rule you cannot satisfy is a conversation, not a suppression comment.

8. Reconcile the contract. Your models can now reject payloads, and every rejection is a response the service produces. Compare what your models actually refuse against section 6 of your contract. Anything missing gets added, with its code and status. Record what you changed and why in a short reconciliation note at the end of docs/payload-triage.md. If nothing was missing, say so and say how you checked.

Out of scope today. service.py and the rule evaluation functions are Day 3's work and are built test-first. api/routes.py is Day 4. Leave both as stubs. If you find yourself writing rule logic in the repository, stop, because the boundary between deciding and doing is the thing you are practicing.

Deliverable
Four files, committed to your branch.

src/claims/models.py, src/claims/repository.py, tests/unit/test_models.py, and tests/unit/test_repository.py.

Plus the reconciliation note in docs/payload-triage.md and any resulting amendment to docs/api-contract.md.



Acceptance criteria
Each criterion is met or not met. There is no partial credit within a criterion.

NotificationRequest rejects a payload containing a field not in the model.
NotificationRequest rejects a payload missing any required field, and no required field has a default.
loss_date is a date type and estimated_amount is a decimal type, in both models, and no date or money value anywhere in the source or the tests is a string or a float.
cancellation_date is typed so that a comparison against it without handling absence fails type checking.
RuleFailure is immutable and carries both a rule identifier and an error code as separate fields.
The repository returns a claim reference matching the format specified in the contract, and no two records share a reference.
Duplicate detection matches on policy_number, loss_date, and claim_type together, and a notification agreeing on only two of the three is not a duplicate.
No rejected notification is recorded, and a test demonstrates that resubmitting it is not treated as a duplicate.
Every field constraint declared in either model has at least one test case that violates it.
Every test uses parametrization with named cases for multiple inputs. No test body contains a loop over cases.
Every fixture returns a fresh object, and the full suite passes when run in any order.
ruff check and mypy both exit zero, with no suppression comment added to achieve it.
No module outside models.py accepts a raw dictionary from a request payload.
The reconciliation note exists, and every code the models can produce appears in contract section 6.


Rubric
Scored out of 100.

Model specification (22 points)
Level	Points	Descriptor
Excellent	22	Every field carries the type and constraint that makes the downstream rule comparison exact. Extras forbidden, nothing optional that is not genuinely optional, and cancellation_date typed so the type checker enforces WI-0158 AC-3. Each choice traces to a contract line.
Proficient	17	Models are correct and complete. One choice is defensible but not the strongest available, such as a constraint expressed in a validator where the type could have carried it, or an optional field whose optionality is not documented.
Developing	11	Models parse valid payloads and reject obviously bad ones, but a money or date field carries a type that makes a boundary comparison unreliable, or extras are permitted, so a misspelled field is silently ignored.
Inadequate	4	Fields are typed loosely enough that structural problems reach the rules, or required fields carry defaults, which means the service invents data the caller did not send.
Repository behavior (18 points)
Level	Points	Descriptor
Excellent	18	Recording, reference generation, and duplicate detection are each separately named and testable. Duplicate matching is exactly the three-field composite. The rejected-notification behavior from WI-0151 AC-3 is a property of the design rather than something the caller has to remember.
Proficient	14	All behaviors are correct. Duplicate detection or reference generation is entangled with recording in a way that makes one of them awkward to test on its own.
Developing	9	Duplicate detection matches on the wrong field set, or references are not reliably unique, or the rejected-notification case works only because no caller has yet done the wrong thing.
Inadequate	3	Rule logic has migrated into the repository, or recording and deciding are not separable, so the boundary the day was about was not established.
Test design and boundary coverage (25 points)
Level	Points	Descriptor
Excellent	25	Every declared constraint has a violating case. Parametrized cases carry ids that identify the failure without opening the file. Test names state the guarantee that breaks, in contract vocabulary. Fixtures are fresh and the suite is order-independent. Coverage of the invalid and edge payloads is deliberate rather than incidental.
Proficient	19	Coverage is thorough and the conventions hold. One or two cases are missing at a constraint, or some ids are present but uninformative, so a pipeline failure requires opening the file.
Developing	12	The obvious cases are covered and the boundaries are not, or several tests share a mutable fixture, or a test loops over inputs internally so one failure hides the others.
Inadequate	5	Tests demonstrate that the models work on good input and little else, or the suite passes only in a particular order.
Code quality and naming (20 points)
Level	Points	Descriptor
Excellent	20	Names use contract vocabulary exactly and no name requires reading the body. No function would need "and" in an honest name. Comments explain why and cite work items where a decision is involved. Nothing restates the code. A reviewer could change any function here without reconstructing the author's context.
Proficient	15	Naming is clear and consistent with the contract. One function is doing slightly more than its name admits, or a comment restates rather than explains.
Developing	10	Names are readable but drift from contract vocabulary in places, or a function has grown past a single responsibility, or decisions that would surprise a reader carry no explanation.
Inadequate	4	Generated structure was accepted without examination. Names are generic, functions are long, and the code reads fluently while remaining expensive for anyone else to change.
Contract reconciliation (15 points)
Level	Points	Descriptor
Excellent	15	Every rejection the models can produce is checked against section 6, gaps are closed with correct codes and statuses, and the note states what was found, what was added, and how the check was performed rather than asserting completeness.
Proficient	11	The reconciliation was done and the contract is now complete, but the note records the outcome without making the method visible, so a reader cannot tell how thorough the check was.
Developing	7	A gap was found and closed, but at least one rejection the models produce still has no entry in section 6, so the service can return a response the contract does not describe.
Inadequate	2	The note asserts that nothing was missing without evidence, or the reconciliation was not attempted and the contract no longer describes what the service does.
