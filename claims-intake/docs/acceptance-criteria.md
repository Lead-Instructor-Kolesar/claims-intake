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