# Rubric

Scored out of 100.

## Model specification (22 points)

| Level | Points | Descriptor |
| --- | ---: | --- |
| Excellent | 22 | Every field carries the type and constraint that makes the downstream rule comparison exact. Extras forbidden, nothing optional that is not genuinely optional, and `cancellation_date` typed so the type checker enforces WI-0158 AC-3. Each choice traces to a contract line. |
| Proficient | 17 | Models are correct and complete. One choice is defensible but not the strongest available, such as a constraint expressed in a validator where the type could have carried it, or an optional field whose optionality is not documented. |
| Developing | 11 | Models parse valid payloads and reject obviously bad ones, but a money or date field carries a type that makes a boundary comparison unreliable, or extras are permitted, so a misspelled field is silently ignored. |
| Inadequate | 4 | Fields are typed loosely enough that structural problems reach the rules, or required fields carry defaults, which means the service invents data the caller did not send. |

## Repository behavior (18 points)

| Level | Points | Descriptor |
| --- | ---: | --- |
| Excellent | 18 | Recording, reference generation, and duplicate detection are each separately named and testable. Duplicate matching is exactly the three-field composite. The rejected-notification behavior from WI-0151 AC-3 is a property of the design rather than something the caller has to remember. |
| Proficient | 14 | All behaviors are correct. Duplicate detection or reference generation is entangled with recording in a way that makes one of them awkward to test on its own. |
| Developing | 9 | Duplicate detection matches on the wrong field set, or references are not reliably unique, or the rejected-notification case works only because no caller has yet done the wrong thing. |
| Inadequate | 3 | Rule logic has migrated into the repository, or recording and deciding are not separable, so the boundary the day was about was not established. |

## Test design and boundary coverage (25 points)

| Level | Points | Descriptor |
| --- | ---: | --- |
| Excellent | 25 | Every declared constraint has a violating case. Parametrized cases carry ids that identify the failure without opening the file. Test names state the guarantee that breaks, in contract vocabulary. Fixtures are fresh and the suite is order-independent. Coverage of the invalid and edge payloads is deliberate rather than incidental. |
| Proficient | 19 | Coverage is thorough and the conventions hold. One or two cases are missing at a constraint, or some ids are present but uninformative, so a pipeline failure requires opening the file. |
| Developing | 12 | The obvious cases are covered and the boundaries are not, or several tests share a mutable fixture, or a test loops over inputs internally so one failure hides the others. |
| Inadequate | 5 | Tests demonstrate that the models work on good input and little else, or the suite passes only in a particular order. |

## Code quality and naming (20 points)

| Level | Points | Descriptor |
| --- | ---: | --- |
| Excellent | 20 | Names use contract vocabulary exactly and no name requires reading the body. No function would need "and" in an honest name. Comments explain why and cite work items where a decision is involved. Nothing restates the code. A reviewer could change any function here without reconstructing the author's context. |
| Proficient | 15 | Naming is clear and consistent with the contract. One function is doing slightly more than its name admits, or a comment restates rather than explains. |
| Developing | 10 | Names are readable but drift from contract vocabulary in places, or a function has grown past a single responsibility, or decisions that would surprise a reader carry no explanation. |
| Inadequate | 4 | Generated structure was accepted without examination. Names are generic, functions are long, and the code reads fluently while remaining expensive for anyone else to change. |

## Contract reconciliation (15 points)

| Level | Points | Descriptor |
| --- | ---: | --- |
| Excellent | 15 | Every rejection the models can produce is checked against section 6, gaps are closed with correct codes and statuses, and the note states what was found, what was added, and how the check was performed rather than asserting completeness. |
| Proficient | 11 | The reconciliation was done and the contract is now complete, but the note records the outcome without making the method visible, so a reader cannot tell how thorough the check was. |
| Developing | 7 | A gap was found and closed, but at least one rejection the models produce still has no entry in section 6, so the service can return a response the contract does not describe. |
| Inadequate | 2 | The note asserts that nothing was missing without evidence, or the reconciliation was not attempted and the contract no longer describes what the service does. |
