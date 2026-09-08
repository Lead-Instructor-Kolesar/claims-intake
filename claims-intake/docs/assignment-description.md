Build the Boundary and the Record
Objective
Implement the two modules that sit at the edges of the service: models.py, which decides what a valid request is, and repository.py, which decides what a recorded claim is. Then write the unit tests that pin both.

Yesterday you specified behavior. Today you build the part of it that has to be true before any business rule runs, and the part that has to be true after one passes. The rule engine between them is tomorrow's work, and it will be much easier to write test-first if the objects it operates on are trustworthy.

Your contract is the specification. Where the contract is silent or wrong, you fix the contract rather than working around it in code.

Prerequisites
Read all four Day 2 articles before starting.

Your Day 1 deliverables are complete and committed: docs/api-contract.md sections 4 through 6, and docs/payload-triage.md.

Confirm the starter material is present. src/claims/policy_client.py ships complete and is not yours to write. It contains the PolicyClient protocol, the PolicyNotFound and PolicyLookupFailed exceptions, and StubPolicyClient, which reads data/policies.json and can be configured to raise either exception on demand. Read it before you start, because your repository tests will use it and Day 3 depends on it heavily.

src/claims/models.py and src/claims/repository.py ship as stubs with signatures and docstrings present and bodies raising NotImplementedError.

Instructions
1. Implement the request model. NotificationRequest parses an incoming payload and rejects anything structurally unacceptable. Every field carries the type that makes the downstream comparison correct, extra fields are forbidden, and no field carries a default that invents data the caller did not send. The Day 2 articles show the shape. Your job is to make every choice in it follow from your contract rather than from the example.

2. Implement the policy model. Policy represents what the policy master returns, including cancellation_date, whose type must make WI-0158 AC-3 difficult to violate rather than merely tested for.

3. Implement the supporting value types. RuleFailure carries a rule identifier and an error code and is immutable. It exists so that a rule identifier can never be passed where an error code is expected. ClaimRecord represents a recorded notification and carries its claim reference.

4. Implement the repository. It stores accepted notifications and returns a claim reference for each. The reference matches the format your contract's success response specifies and is unique across all records. Two behaviors are load bearing and both come from WI-0151. The repository can tell you whether a notification duplicates an existing record, matching on policy_number, loss_date, and claim_type together. And a notification that was rejected is not recorded at all, so it can never be the thing a later submission duplicates.

5. Write the model tests. tests/unit/test_models.py. Cover what the model accepts and what it refuses, using parametrization with named cases rather than one test per input or a loop inside one test. Every field constraint you declared gets a case that violates it. The payloads in data/fnol_invalid.json and data/fnol_edge.json are your source of realistic inputs, and you should be able to state for each one whether it fails at the model or survives to the rules.

6. Write the repository tests. tests/unit/test_repository.py. Cover recording, reference uniqueness, duplicate detection including the case where only two of the three matching fields agree, and the WI-0151 AC-3 behavior that a rejected notification leaves nothing to duplicate. Fixtures build fresh objects. No test may depend on another test having run.

7. Run the tools and fix what they find. ruff check and mypy both exit clean. A rule you cannot satisfy is a conversation, not a suppression comment.

8. Reconcile the contract. Your models can now reject payloads, and every rejection is a response the service produces. Compare what your models actually refuse against section 6 of your contract. Anything missing gets added, with its code and status. Record what you changed and why in a short reconciliation note at the end of docs/payload-triage.md. If nothing was missing, say so and say how you checked.

Out of scope today. service.py and the rule evaluation functions are Day 3's work and are built test-first. api/routes.py is Day 4. Leave both as stubs. If you find yourself writing rule logic in the repository, stop, because the boundary between deciding and doing is the thing you are practicing.

Deliverable
Four files, committed to your branch.

src/claims/models.py, src/claims/repository.py, tests/unit/test_models.py, and tests/unit/test_repository.py.

Plus the reconciliation note in docs/payload-triage.md and any resulting amendment to docs/api-contract.md.

Lab component produced
Component C2 of the week's lab. Day 3 builds the rule engine against these objects and will not touch raw payloads. Day 4 wires the HTTP surface to them and asserts the status codes your models produce.

Interface contract fixed and consumed
Consumes C1. Every type, constraint, and code in this work traces to docs/api-contract.md.

Fixes C2. NotificationRequest, Policy, RuleFailure, and ClaimRecord with their field names, types, and constraints. The repository surface: recording, reference generation, and duplicate detection. The unit test layout and naming convention.

Changing C2 after today means changing code Day 3 has already been written against.