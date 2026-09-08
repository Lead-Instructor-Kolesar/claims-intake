# W1-02 Requirements Plan

This document is a study guide and an implementation brief for Day 2 of the claims intake lab. Read it to understand what the assignment is actually testing, which decisions the types must encode, and how each requirements step maps to acceptance criteria and the rubric. Implement from it later; this file is not itself a Day 2 deliverable.

The assignment source of truth is [`docs/W1-02-requirements.md`](W1-02-requirements.md). The service's authority on behaviour is [`docs/api-contract.md`](api-contract.md). Where the assignment wording and the contract disagree, the contract wins.

---

## 1. Main goal

Day 2 is not "write some Pydantic models." It is to put a hard boundary in front of the rules so that three different kinds of work stay in three different places:

| Layer | Module | Question it answers | When |
| --- | --- | --- | --- |
| Shape | `src/claims/models.py` | Can this payload even be interpreted as a notification? | Day 2 |
| Admissibility | `src/claims/service.py` | Given a well-formed notification and a policy, is it allowed? | Day 3 |
| Recording | `src/claims/repository.py` | Persist an accepted notification and answer queries about what has been written | Day 2 (store only) |

A payload that is not well formed never becomes a typed object. A typed object that reaches the rule layer has already been proven structurally valid. A notification that was refused is never written, so it can never be the thing a later submission duplicates.

That boundary is what the rubric means by "the day was about." If rule logic lands in the repository, or if a misspelled JSON field is silently ignored, the day has failed even if tests pass on happy-path input.

The two work items you encode today, without implementing their rule evaluation, are:

- **WI-0151** (duplicates): the repository can *query* the three-field composite. HTTP 409 and `DUPLICATE_NOTIFICATION` are Day 3/4. The store must make AC-3 true by construction: there is no way to persist a rejection.
- **WI-0158** (cancellation): `Policy.cancellation_date` is typed so a comparison without handling absence fails type checking. `POLICY_CANCELLED` evaluation is Day 3.

---

## 2. What you need to do to gain understanding

Work through these in order. Each one answers a question the code will force you to take a position on. If you skip them, you will invent a constraint the contract did not state, or leave a constraint as a validator that the type should have carried.

### 2.1 Contract sections 2.2, 2.3, and 2.4

[`docs/api-contract.md`](api-contract.md) sections 1 through 3 are fixed. Do not edit them. Day 2 models are built against 2 and 3.

**Section 2.2** lists the five request fields, which are required, and the notes that become field constraints:

- `policy_number`: string, required, not empty. No MOT-XXXX pattern is stated; do not invent one.
- `loss_date`: calendar date `YYYY-MM-DD` on the wire; in Python it must be `date`, not `str`.
- `claim_type`: one of the values in 2.3, not empty.
- `estimated_amount`: decimal, USD, two decimal places, greater than zero. In Python it must be `Decimal`, not `float` and not `str`.
- `description`: optional free text. Absent and `null` are equivalent. This is the only field that may have a default, because the default (`None`) does not invent caller data; it is the contract's stated equivalence.

The paragraph under the table is load-bearing: extra fields are forbidden. A misspelled field accepted-and-ignored would record a notification built from data the caller did not send. That is the Developing failure mode on the model rubric ("extras are permitted, so a misspelled field is silently ignored").

**Section 2.3** splits two questions that are easy to collapse:

1. Is `claim_type` one of `collision`, `theft`, `glass`, `liability`, `weather`? That is vocabulary. It is structural. It belongs on the model.
2. Is that type permitted on *this policy's product*? That is V-5. It belongs in `service.py` on Day 3.

EDGE-11 sends `flood`. If the model types `claim_type` as a plain `str`, `flood` survives to the rules and V-5 reports `TYPE_NOT_COVERED`, which is a lie: the type was never in the contract vocabulary. If the model types it as a `Literal` of the five values, `flood` dies at parse time. That is the choice "every field carries the type that makes the downstream comparison exact."

**Section 2.4** is the 400 / 422 split, stated once:

- **400**: the request cannot be interpreted. Invalid JSON, missing required field, wrong type, extra field. The caller's *code* is wrong.
- **422**: the request was interpreted and the content is not admissible. The caller's *data* is wrong.

The assignment step 1 says "rejects anything structurally unacceptable (422)." That is a slip. Follow the contract. Models do not return HTTP statuses at all; they refuse to parse (Pydantic `ValidationError`). Day 4 maps that refusal to **400**. Day 3 maps rule failures to **422** (and 409 for duplicates). If you find yourself putting a status code on a model, stop.

### 2.2 Contract section 3

Success is `201` with `claim_reference` matching `CLM-YYYY-NNNNNN` and `status: recorded`.

- `YYYY` is the calendar year in which the notification was **recorded**, not the loss year.
- `NNNNNN` is a zero-padded sequence.
- A reference is unique across all recorded notifications and is never reissued.
- A refused notification is never recorded and no claim reference is issued. There is no partial outcome.

This is why the repository has no `reject()` that writes. Recording is the only write. WI-0151 AC-3 falls out of that design rather than being a check the caller has to remember.

### 2.3 WI-0151 — duplicates live in the store, not the rule table

From [`docs/requirements-brief.md`](requirements-brief.md):

- AC-1: match on `policy_number`, `loss_date`, and `claim_type` **together**. Two of three is not a duplicate.
- AC-2: HTTP 409, code `DUPLICATE_NOTIFICATION`, existing `claim_reference` in `detail`. **Not today.** The repository returns the existing record or `None`. Day 3 turns that into a `ValidationOutcome`. Day 4 turns that into 409.
- AC-3: a previous *rejected* submission is not a duplicate, because nothing was written.

The repository docstring already says this: the duplicate check is a query against what has been recorded, which is why it belongs here rather than in the rule table. `find_matching` is that query. `record` must not call it and refuse; that would move deciding into doing.

### 2.4 WI-0158 — type the absence, do not evaluate the rule

A cancelled policy keeps its original `expiry_date`. Cover has ended, but a naive V-3 (`loss_date <= expiry_date`) would still accept a loss inside the original term. That is why cancellation is its own rule (V-7, Day 3) and why it must outrank "after expiry" when both are true (AC-4).

Today you only type `cancellation_date` so that:

- a comparison against it without handling absence fails mypy (AC-3: null means "not cancelled, this rule does not apply");
- the field is genuinely optional in the domain (`date | None`), but **required to pass** when constructing a `Policy` (no `= None` default that lets you forget it).

You do **not** write `if loss_date >= cancellation_date`. That is Day 3.

### 2.5 `PolicyRecord` is the source of `Policy`

[`src/claims/policy_client.py`](../src/claims/policy_client.py) already ships complete. `PolicyRecord` is a plain object, deliberately not Pydantic, and it is what you build `Policy` from:

- `policy_number: str`
- `product: str`
- `effective_date: date`
- `expiry_date: date`
- `cancellation_date: date | None`
- `limit: Decimal`
- `permitted_claim_types: tuple[str, ...]`

Dates and money are already `date` / `Decimal` here. If `Policy` stores them as `str` or `float`, you have undone that work and failed the AC that both models use `date` and `Decimal`.

Do not parse a raw dict from the policy master in any module except the client, which already does. A `Policy.from_record(record: PolicyRecord)` factory on the model is a good way to keep that conversion in one place without teaching another module to accept a dict.

### 2.6 Classify every realistic payload before writing tests

The assignment says the payloads in `data/fnol_invalid.json` and `data/fnol_edge.json` are your source of realistic inputs, and you should be able to state for each one whether it fails at the model or survives to the rules. Do that classification now. It is the difference between Excellent test coverage ("deliberate rather than incidental") and hoping a parametrize over the files happens to hit the interesting cases.

See section 4 below.

### 2.7 Prerequisite: Day 1 contract work on this branch

On this branch, [`docs/api-contract.md`](api-contract.md) sections 4 through 6 are filled. The rule table includes V-6 (WI-0151) and V-7 (WI-0158), evaluation order is `V-1, V-2, V-7, V-3, V-4, V-5, V-6`, the error envelope is specified, and section 6 already maps `MALFORMED_REQUEST` at 400. The EDGE-07 / EDGE-11 / EDGE-12 decisions are in section 4 and in [`docs/payload-triage.md`](payload-triage.md).

That does **not** change what Day 2 implements. NotificationRequest is specified by sections 2 and 3. It does mean:

- Step 8 (reconcile against section 6) is a check against an existing `MALFORMED_REQUEST` row, not a fill-in of an empty heading. The Day 2 reconciliation note in `payload-triage.md` already records that check.
- You still implement the WI-0151 *query* and the WI-0158 *type* from the work items. V-6 and V-7 are in the table; you do not *evaluate* them.
- You do not implement V-6/V-7 evaluation. You do not rewrite sections 4–6. You confirm that every refusal the models can produce already has a code in section 6.

---

## 3. Starting point in the code

### 3.1 `src/claims/models.py`

Three stubs:

- `NotificationRequest` has only `policy_number: str`. The docstring says every other field, and every constraint including this one, is Day 2's work. It also states the boundary: the model is responsible for the shape of the request and for nothing else.
- `Policy` is empty. It exists so the rules have typed fields to compare against.
- `RecordedNotification` is empty. It carries the claim reference. Contract section 3 fixes the format.

The assignment text calls the recorded type `ClaimRecord`. The shipped stub, and `service.py` which you must not edit, already use `RecordedNotification`. **Implement `RecordedNotification`.** Treat "ClaimRecord" in the assignment as the same concept.

### 3.2 `src/claims/repository.py`

Three methods, all `NotImplementedError`:

- `__init__`
- `record(notification: object) -> RecordedNotification` — change `object` to `NotificationRequest`. That is the AC "no module outside models.py accepts a raw dictionary from a request payload."
- `find_matching(policy_number, loss_date, claim_type) -> RecordedNotification | None` — already named and already documents WI-0151 AC-1 and AC-3.

The module docstring already warns you: if you find yourself writing rule logic here, stop.

### 3.3 Leave these as stubs

- `src/claims/service.py` — `ValidationOutcome` already lives here. Day 2 adds `RuleFailure` in `models.py` and does **not** merge the two or rewrite `evaluate_*`.
- `src/claims/api/routes.py` — Day 4.
- `src/claims/policy_client.py` — complete. Do not edit.

### 3.4 Tests

[`tests/conftest.py`](../tests/conftest.py) has `policy_client` only. There is no `tests/unit/` yet. You will add `test_models.py` and `test_repository.py`, and you will likely add factory fixtures to `conftest.py`. Those factories are supporting work, not one of the four named deliverable files.

### 3.5 Tooling

[`pyproject.toml`](../pyproject.toml): Python >= 3.12, Pydantic, FastAPI, `mypy` with `strict = true` on `src` and `tests`, ruff line-length 100. No Pydantic mypy plugin is configured. If strict mypy cannot see Pydantic field types, adding `plugins = ["pydantic.mypy"]` is a config change, not a suppression comment.

---

## 4. Payload classification: model failure vs survives to rules

A payload **fails at the model** if `NotificationRequest.model_validate(payload)` raises. It **survives to the rules** if it becomes a `NotificationRequest`. What the rules would then do is listed for orientation only; you do not implement those rules today.

JSON wire values may be strings (`"4200.00"`, `"2026-04-02"`). That is the HTTP body. After parse, Python values must be `Decimal` and `date`. The AC "no date or money value anywhere in the source or the tests is a string or a float" applies to **Python source and test construction**, not to the JSON fixtures.

### 4.1 `data/fnol_invalid.json` — all seven survive the model

These are business-rule failures. They are well formed.

| ID | Why it is well formed | What the rules would do (Day 3+) |
| --- | --- | --- |
| INVALID-01 | All five fields present, types valid, `collision` in vocabulary | V-1 `POLICY_NOT_FOUND` (`MOT-9999` is not in the master) |
| INVALID-02 | Well formed | V-2 `LOSS_BEFORE_INCEPTION` (loss 2026-02-20, inception 2026-03-15) |
| INVALID-03 | Well formed | V-3 `LOSS_AFTER_EXPIRY` (loss 2026-03-20, expiry 2026-02-28) |
| INVALID-04 | Well formed | V-4 `AMOUNT_EXCEEDS_LIMIT` (14500.00 against limit 10000.00) |
| INVALID-05 | `collision` is in the vocabulary | V-5 `TYPE_NOT_COVERED` (liability-only product) |
| INVALID-06 | Well formed; context says VALID-01 already recorded | WI-0151 / V-6 `DUPLICATE_NOTIFICATION` (same policy, date, type as VALID-01) |
| INVALID-07 | Well formed; cancellation is not a parse problem | WI-0158 / V-7 `POLICY_CANCELLED` (loss after cancellation, still inside original term) |

If any of these fail `model_validate`, a constraint is too tight (for example treating "exists in the master" as a field constraint).

### 4.2 `data/fnol_edge.json`

| ID | Model or rules | Reason |
| --- | --- | --- |
| EDGE-01 | Survives | Loss on inception date. Inclusive boundary (WI-0142 AC-3). Accepted by rules. |
| EDGE-02 | Survives | Amount equal to limit. Inclusive boundary. Accepted by rules. |
| EDGE-03 | Survives | Loss on expiry date. Inclusive. Accepted by rules. |
| EDGE-04 | Survives | Loss on the cancellation date. That is WI-0158 AC-2, a rule, not a shape problem. |
| EDGE-05 | Survives | Before inception *and* above the limit. Multi-rule. V-2 would win on evaluation order. Still well formed. |
| EDGE-06 | Survives | Above the limit on a product that permits collision. V-4. |
| EDGE-07 | Survives | `mot-4471` is a non-empty string. Exact string equality with the master (Decision 1 / §4); V-1 `POLICY_NOT_FOUND`. Not a missing-field or type problem. |
| EDGE-08 | **Fails at the model** | `estimated_amount` omitted. Required field missing. Section 2.4 → 400. |
| EDGE-09 | Survives | `collision` is in the vocabulary; named-perils product does not permit it. V-5. |
| EDGE-10 | Survives | Cancelled *and* after original expiry. Well formed. V-7 is evaluated before V-3, so the rules return `POLICY_CANCELLED` (WI-0158 AC-4). |
| EDGE-11 | **Fails at the model** | `flood` is not in section 2.3. Vocabulary is structural. `MALFORMED_REQUEST` 400, not V-5 (Decision 2 / §4). |
| EDGE-12 | **Fails at the model** | `3499.999` has three decimal places. Section 4 `invalid_scale`. `MALFORMED_REQUEST` 400 (Decision 3). |

EDGE-07, EDGE-11, and EDGE-12 are the payloads Day 1 had to decide. Those decisions are now in contract section 4 and the triage decision log. Day 2 is where EDGE-11 and EDGE-12 become types (`Literal` claim type; `decimal_places=2`). EDGE-07 stays a string; do not silently uppercase it on the model, because that would invent data the caller did not send.

### 4.3 `data/fnol_valid.json`

All eight are well formed and should parse. VALID-06 omits `description`; that is allowed. Use them as accept-cases, not as the only accept-cases.

---

## 5. Concrete steps

Each step below is one item from [`docs/W1-02-requirements.md`](W1-02-requirements.md). For each: what to do, which files, which ACs, how it scores on the rubric, and what "Excellent" requires that "merely works" does not.

---

### Step 1. Implement `NotificationRequest`

**Requirements item 1.** Parse the payload. Reject anything structurally unacceptable. Every field carries the type that makes the downstream comparison correct, extra fields are forbidden, and no field carries a default that invents data the caller did not send. Choices follow from the contract, not from an article's example.

**File:** [`src/claims/models.py`](../src/claims/models.py)

**Recommended shape** (choices traced to contract lines):

```python
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

class NotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_number: Annotated[str, Field(min_length=1)]
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Annotated[Decimal, Field(gt=0, decimal_places=2, max_digits=12)]
    description: str | None = None
```

Why each choice:

| Choice | Contract line | What happens if you choose weaker |
| --- | --- | --- |
| `extra="forbid"` | §2.2 extra fields rejected | Misspelled field silently dropped. Developing on model rubric. |
| No default on the four required fields | §2.2 required = yes; AC "no required field has a default" | Service invents data. Inadequate. |
| `min_length=1` on `policy_number` | §2.2 "Not empty" | Empty string reaches V-1 as a real lookup. |
| `loss_date: date` | AC: date type; §2.2 `YYYY-MM-DD` | String comparison on dates is lexicographic luck, not a date comparison. Developing. |
| `claim_type: ClaimType` (Literal) | §2.3 vocabulary vs V-5 subset | `flood` becomes `TYPE_NOT_COVERED`. Wrong person, wrong code. |
| `Decimal` + `gt=0` + `decimal_places=2` on the type/Field | §2.2; rubric: type carries the constraint, not a validator if the type can | Float money makes `<= limit` unreliable. Developing. |
| `description: str \| None = None` | §2.2 optional; absent ≡ null | Making it required rejects VALID-06. Omitting the default and the `None` makes absent fail. |

**Float money.** JSON numbers like `3499.999` may arrive as `float`, which cannot represent decimal money exactly. `Decimal` will coerce a float if you let it. The strongest available choice is: coerce from `str` and `int` (the data files use strings), reject `float`. A small `BeforeValidator` that rejects `float` is justified here because the type alone, without `strict` mode, will accept floats; turning on full strict mode would also reject the JSON strings. The rubric's "validator where the type could have carried it" is about using a validator for `gt=0` instead of `Field(gt=0)`, not about this.

**Do not** put policy-existence, date-vs-inception, or amount-vs-limit on this model. Those are rules. The model docstring already says so.

**Acceptance criteria this step meets:**

- NotificationRequest rejects a payload containing a field not in the model.
- NotificationRequest rejects a payload missing any required field, and no required field has a default.
- `loss_date` is a date type and `estimated_amount` is a decimal type (this model).
- No module outside `models.py` accepts a raw dictionary from a request payload (the parse happens here; everyone else receives `NotificationRequest`).

**Rubric:** Model specification (22). Excellent is 22: extras forbidden, nothing optional that is not genuinely optional, every type making downstream comparison exact, each choice traces to a contract line. Proficient (17) is "one choice is defensible but not the strongest" — that is the trap of a validator for something `Field`/`Literal`/`date` could have expressed, or `description: str = ""` inventing an empty string.

**Code quality (20):** name the type alias `ClaimType` after section 2.3, not `AllowedStr`. Comment only where a decision is involved (why float is rejected; why `description` defaults to `None`). Cite the contract section or work item, do not restate the field list.

---

### Step 2. Implement `Policy`

**Requirements item 2.** Policy represents what the policy master returns, including `cancellation_date`, whose type must take WI-0158. (The assignment writes `cancellation_data` once; the field name in `PolicyRecord` and the work item is `cancellation_date`.)

**File:** [`src/claims/models.py`](../src/claims/models.py)

**Recommended shape:**

```python
class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_number: Annotated[str, Field(min_length=1)]
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None  # required argument, no default
    limit: Decimal
    permitted_claim_types: tuple[ClaimType, ...]
```

Optional factory, keeps dicts out of other modules:

```python
@classmethod
def from_record(cls, record: PolicyRecord) -> Policy: ...
```

If `from_record` would import `PolicyRecord` and create a cycle, construct `Policy(...)` at the call site on Day 3 instead. Do not add the factory just to have one.

**WI-0158 encoded as a type, not as a rule:**

- Type is `date | None`. `loss_date >= policy.cancellation_date` fails mypy because you cannot compare `date` with `date | None` until you narrow. That is the AC "cancellation_date is typed so that a comparison against it without handling absence fails type checking."
- **No `= None` default.** Null is a real value from the master (WI-0158 AC-3). If the field defaults to `None`, you can construct a `Policy` without mentioning cancellation and silently treat it as not cancelled. Required-but-nullable is the strongest choice: you must pass it, and `None` means "not cancelled."
- Do not implement AC-1, AC-2, or AC-4. Those compare `loss_date` to `cancellation_date` and choose `POLICY_CANCELLED` over `LOSS_AFTER_EXPIRY`. Day 3.

`limit: Decimal` (not `float`) is the other half of the AC "in both models." `permitted_claim_types: tuple[ClaimType, ...]` makes the V-5 membership check a typed comparison against the same vocabulary as the request.

`product` stays `str`. The contract does not enumerate product names.

**Acceptance criteria this step meets:**

- `loss_date` / `estimated_amount` (here: `effective_date`, `expiry_date`, `cancellation_date`, `limit`) are `date` / `Decimal` on both models.
- `cancellation_date` is typed so a comparison without handling absence fails type checking.

**Rubric:** Model specification (22), specifically "cancellation_date typed so the type checker enforces WI-0158 AC-3." A default of `None` is the Proficient miss ("an optional field whose optionality is not documented" / weaker than required-but-nullable). Putting cancellation *logic* on Policy or in the repository is out of scope and risks the repository rubric's Inadequate ("rule logic has migrated into the repository").

---

### Step 3. Implement `RuleFailure` and `RecordedNotification`

**Requirements item 3.** `RuleFailure` carries a rule identifier and an error code and is immutable. It exists so that a rule identifier can never be passed where an error code is expected. `ClaimRecord` / `RecordedNotification` represents a recorded notification and carries its claim reference.

**File:** [`src/claims/models.py`](../src/claims/models.py)

**`RuleFailure`.** Use a frozen dataclass, not a Pydantic model. It is not a request payload; using Pydantic would invite `model_validate(dict)` from other modules.

```python
RuleIdentifier = NewType("RuleIdentifier", str)
ErrorCode = NewType("ErrorCode", str)

@dataclass(frozen=True)
class RuleFailure:
    rule: RuleIdentifier
    code: ErrorCode
```

Why two types, not two `str` fields: the assignment says this type exists *so that* a rule identifier cannot be passed where an error code is expected. Two `str` fields are immutable if frozen, but `RuleFailure(rule="POLICY_NOT_FOUND", code="V-1")` type-checks. `NewType` (or two Enums) makes that a type error. Enums of every code couple Day 2 to the full rule table, which is Day 3's job and is incomplete on this branch; `NewType` is enough.

Do not replace `ValidationOutcome` in `service.py`. Day 3 may later wrap or adopt `RuleFailure`. Today they coexist.

**`RecordedNotification`.** The stub name stays. It must carry:

- `claim_reference: str` matching `CLM-YYYY-NNNNNN` (a pattern constraint on the type is appropriate; the repository is what *issues* the value).
- `policy_number`, `loss_date`, `claim_type` — without these, `find_matching` has nothing to compare. Duplicate detection is a query against recorded notifications, so the record is the thing that holds the composite.
- Optionally `estimated_amount` and `description`, so the record is the notification-as-written rather than a key plus a reference. Include them; a recorded notification that drops the amount is a surprising narrowing.

Use `date` and `Decimal` here too. The AC says no date or money value anywhere in the source is a string or a float.

**Acceptance criteria this step meets:**

- `RuleFailure` is immutable and carries both a rule identifier and an error code as separate fields.

**Rubric:** Model specification (the recorded type's dates/money); Code quality (20) — names use contract vocabulary (`claim_reference`, not `id` or `claim_id`). A comment on `RuleFailure` should cite *why* the two types are distinct, not restate that the class has two fields.

---

### Step 4. Implement the repository

**Requirements item 4.** Store accepted notifications. Return a claim reference matching section 3. Unique across all records. Two load-bearing behaviours from WI-0151: (1) duplicate query on the three-field composite; (2) a rejected notification is not recorded, so it can never be duplicated.

**File:** [`src/claims/repository.py`](../src/claims/repository.py)

**Excellent on Repository behavior (18) requires three separately named, separately testable behaviours.** Entangling them is Proficient (14): "duplicate detection or reference generation is entangled with recording in a way that makes one of them awkward to test on its own." Putting 409 / `DUPLICATE_NOTIFICATION` / cancellation into this module is Inadequate (3).

Recommended split:

```python
class NotificationRepository:
    def __init__(self) -> None:
        self._records: list[RecordedNotification] = []
        self._sequence: int = 0

    def issue_claim_reference(self, recorded_on: date) -> str:
        """Return the next CLM-YYYY-NNNNNN. Never reissued."""

    def record(
        self,
        notification: NotificationRequest,
        recorded_on: date | None = None,
    ) -> RecordedNotification:
        """Write the notification. Always writes. Does not decide duplicates."""

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> RecordedNotification | None:
        """WI-0151 AC-1: all three fields. Recorded notifications only."""
```

Keep the public names `record` and `find_matching` as shipped. Add `issue_claim_reference` (or equivalent) so reference generation can be tested without going through `record`, and so `record` does not hide a second responsibility. `recorded_on` defaults to `date.today()` inside `record` so production call sites stay simple, but tests can pass an explicit date and pin `YYYY`. That avoids a suite that is secretly date-dependent.

**What `record` does not do:**

- Does not call `find_matching` and refuse. Deciding is Day 3's `submit_notification`. If `record` rejects duplicates, you have moved V-6 into the store.
- Does not take a `dict`. Signature is `NotificationRequest`.
- Does not have a `reject()` or `record_failure()`. WI-0151 AC-3 is then a property of the design: the only write is `record`, and `find_matching` only reads `_records`. A caller cannot "forget" to skip rejected notifications because there is nothing to forget.

**Reference format:** `CLM-{recorded_on.year:04d}-{sequence:06d}`. Sequence increments and is never reused, including after a process that only called `issue_claim_reference`. Uniqueness is across all records, not per year; the contract says unique across all recorded notifications. Using year in the string plus a monotonically increasing sequence satisfies that.

**`find_matching`:** equality on all three fields. `estimated_amount` and `description` do not participate (WI-0151 AC-1 names three fields; naming fewer or more is Developing). Return the existing `RecordedNotification` so Day 3 can put `claim_reference` in `detail` (AC-2) without the repository knowing what an error envelope is.

**Acceptance criteria this step meets:**

- The repository returns a claim reference matching the format specified in the contract, and no two records share a reference.
- Duplicate detection matches on `policy_number`, `loss_date`, and `claim_type` together, and a notification agreeing on only two of the three is not a duplicate.
- No rejected notification is recorded (by design: no reject-write path).
- No module outside `models.py` accepts a raw dictionary from a request payload.

**Rubric:** Repository behavior (18). Excellent: the three behaviours separately named and testable; three-field composite exactly; AC-3 a property of the design. Code quality (20): `find_matching` is the contract/WI name for the query; do not call it `check_duplicate` (that name decides). A comment on `record` should cite WI-0151 AC-3 as the reason there is no reject path, not "appends to a list."

---

### Step 5. Write `tests/unit/test_models.py`

**Requirements item 5.** Cover what the model accepts and what it refuses. Parametrization with named cases. Every declared constraint gets a violating case. `fnol_invalid.json` and `fnol_edge.json` are realistic inputs; state for each whether it fails at the model or survives to the rules.

**File to add:** `tests/unit/test_models.py`

**Conventions for Test design (25) Excellent:**

- `@pytest.mark.parametrize(..., ids=...)` where ids identify the failure without opening the file: `unknown_field`, `missing_estimated_amount`, `empty_policy_number`, `claim_type_not_in_vocabulary`, `amount_three_decimal_places`, `amount_not_greater_than_zero`, `loss_date_not_a_date`. Uninformative ids (`case0`, `invalid`) are the Proficient miss.
- Test names state the guarantee that breaks, in contract vocabulary: `test_notification_request_rejects_unknown_field`, not `test_extra`.
- No loop over cases inside a test body. One failure must not hide the others.
- Fixtures / factories return a **fresh** object every time. A shared mutable `NotificationRequest` used by two tests makes the suite order-dependent (Developing).
- Coverage of invalid and edge payloads is **deliberate**: a parametrized test that names INVALID-01..07 and EDGE-01..12 and asserts `parses` vs `raises`, matching section 4 of this document.

**Every constraint gets a violating case.** Inventory what you declared, then write the case. If you cannot point from a `Field`/`Literal`/`extra="forbid"` to a row in the parametrize, the AC "every field constraint declared in either model has at least one test case that violates it" is not met. There is no partial credit.

Suggested groups (each group is one parametrized test, not one test per row):

1. **Accepts well-formed payloads** — VALID-01..08 plus INVALID-* and EDGE-* that survive (all except EDGE-08, EDGE-11, EDGE-12). Assert type of `loss_date` is `date` and type of `estimated_amount` is `Decimal`.
2. **Rejects unknown field** — extra key on an otherwise valid body. AC extra-field.
3. **Rejects missing required field** — four cases: `policy_number`, `loss_date`, `claim_type`, `estimated_amount`. Include EDGE-08 as the realistic amount-omitted case.
4. **Rejects empty `policy_number`**.
5. **Rejects claim type not in vocabulary** — `flood` (EDGE-11), `""`, a misspelling.
6. **Rejects amount that is not greater than zero** — `0`, negative.
7. **Rejects amount with excess decimal places** — EDGE-12 `3499.999`.
8. **Rejects float money** if you declared that constraint.
9. **Rejects `loss_date` that is not a date** — wrong type, unparsable string.
10. **`description` absent and `null` are equivalent** — both become `None`.
11. **Required fields have no defaults** — inspect the model fields; `policy_number` / `loss_date` / `claim_type` / `estimated_amount` must not have defaults. This is the AC, not just "missing is rejected."
12. **Policy constraints** — `cancellation_date` accepts `None` and `date`; rejects a string. `limit` is `Decimal`. `effective_date` / `expiry_date` are `date`. If `Policy` forbids extras, a violating case for that too.
13. **`RuleFailure` is immutable** — assignment to `rule` or `code` raises. Constructing with swapped types is a mypy-level guarantee; a unit test can still show frozen behaviour.
14. **Deliberate payload classification** — one parametrized test, ids `INVALID-01` … `EDGE-12`, expected `model` or `rules`.

**Python construction in tests uses `date(...)` and `Decimal("...")`.** When you are not going through JSON, never write `loss_date="2026-04-02"` or `estimated_amount=4200.00` or `estimated_amount="4200.00"` as the model constructor arguments. Loading the JSON fixtures and passing them to `model_validate` is the exception: that is the wire format.

**Acceptance criteria this step meets:**

- Extra field rejected (tested).
- Missing required field rejected; no defaults (tested).
- Dates/money typed; tests do not use string/float money or dates in Python construction.
- Every field constraint has a violating case.
- Parametrization with named cases; no loop over cases in a test body.
- Fixtures return fresh objects; suite order-independent.
- Payload classification of invalid and edge files is explicit.

**Rubric:** Test design (25). Excellent is 25. The failure modes to avoid: missing a constraint case; ids that require opening the file; a test that `for payload in payloads:`; a module-scoped mutable fixture; only testing happy path (Inadequate, 5).

---

### Step 6. Write `tests/unit/test_repository.py`

**Requirements item 6.** Cover recording, reference uniqueness, duplicate detection including only-two-of-three, and WI-0151 AC-3. Fixtures build fresh objects. No test depends on another having run.

**File to add:** `tests/unit/test_repository.py`

**Supporting:** factory fixtures in [`tests/conftest.py`](../tests/conftest.py), for example `make_notification() -> NotificationRequest` and `repository() -> NotificationRepository`. Each call returns a new instance. Do not yield a shared in-memory list of records.

Cover, as separate tests (parametrize where there are multiple inputs):

1. **`record` returns a `claim_reference` matching `CLM-YYYY-NNNNNN`.** Use an explicit `recorded_on` so `YYYY` is asserted, not assumed to be "this year."
2. **No two records share a reference.** Record several; collect references; assert uniqueness. Sequence padding (`000001`, `000002`).
3. **References are never reissued** — if you expose `issue_claim_reference`, two calls produce two values even if the first was not stored. If you do not expose it, uniqueness of `record` is the observable.
4. **`find_matching` returns the recorded notification when all three fields agree.** Assert it is the same `claim_reference`.
5. **Only two of three is not a duplicate.** Three named cases: different `policy_number`, different `loss_date`, different `claim_type`. Ids such as `differing_policy_number`, `differing_loss_date`, `differing_claim_type`.
6. **WI-0151 AC-3:** construct a well-formed notification. Do **not** call `record`. `find_matching` on those three fields returns `None`. Then `record` it; it is stored. That is "a rejected notification leaves nothing to duplicate" without the repository knowing about rejection. The test demonstrates the design property: only `record` writes.
7. Optionally: `record` does not refuse a second write with the same three fields. Day 3 is what calls `find_matching` first. If your tests require `record` to reject duplicates, you have put V-6 in the repository.

**Acceptance criteria this step meets:**

- Reference format and uniqueness.
- Three-field duplicate detection; two-of-three is not a duplicate.
- No rejected notification is recorded, and a test demonstrates that resubmitting (matching a never-recorded payload) is not treated as a duplicate.
- Fresh fixtures; order-independent suite.
- Parametrization with named cases for the multiple-input tests.

**Rubric:** Test design (25) and Repository behavior (18). The AC-3 test is what makes AC-3 "a property of the design rather than something the caller has to remember" *visible*. If the test instead calls a fictional `reject()` and then checks a flag, you have invented an API the design was not supposed to have.

---

### Step 7. Run ruff and mypy; fix what they find

**Requirements item 7.** `ruff check` and `mypy` both exit clean. A rule you cannot satisfy is a conversation, not a suppression comment.

From the repo root (the directory with `pyproject.toml`):

```
uv run pytest
uv run ruff check .
uv run mypy
```

**Do not** add `# noqa`, `# type: ignore`, or per-file ignores to buy a pass. That fails the AC regardless of whether the tools exit zero.

Likely issues and the honest fix:

- Strict mypy does not treat Pydantic fields as typed → add `plugins = ["pydantic.mypy"]` under `[tool.mypy]` in `pyproject.toml`. Config, not suppression.
- `record(self, notification: object)` was a stub. After changing to `NotificationRequest`, mypy should be happier, not worse.
- `date | None` compared without a guard is *supposed* to fail mypy in rule code. There is no rule code today. Do not "fix" `Policy.cancellation_date` to `date` to silence a future comparison.
- Unused imports, line length 100.

**Acceptance criteria:** ruff check and mypy both exit zero, with no suppression comment added to achieve it.

**Rubric:** this is a binary AC, not its own rubric row, but Code quality (20) suffers if the file is littered with ignores or if names were chosen to dodge the type checker.

---

### Step 8. Reconcile the contract

**Requirements item 8.** Models can now reject payloads, and every rejection is a response the service produces. Compare what the models actually refuse against section 6. Anything missing gets added, with its code and status. Record what changed and why in a short reconciliation note at the end of [`docs/payload-triage.md`](payload-triage.md). If nothing was missing, say so and say how you checked.

**Files:**

- [`docs/payload-triage.md`](payload-triage.md) — the Day 2 reconciliation note is already appended. Do not rewrite the Day 1 classification or decision log; the note is a separate section at the end.
- [`docs/api-contract.md`](api-contract.md) — **section 6 only**, and only if a model-produced code is missing. Sections 1–3 are fixed. Day 1 already filled sections 4–6 (V-6, V-7, envelope, dependency 5xx, `MALFORMED_REQUEST`). Do not redo that work. On this branch the inventory found no missing model-produced code, so section 6 was not amended.

**What "codes the models can produce" means.** Pydantic raises `ValidationError`; it does not emit `LOSS_BEFORE_INCEPTION`. The models refuse. Day 4 will map that refusal onto the error envelope. The contract must name the code and status for that class of refusal so the service cannot return a response the contract does not describe.

Section 2.4 already groups every uninterpretable request as **400**: invalid JSON, missing required field, wrong type, extra field. Empty `policy_number`, `flood`, three decimal places, and amount `<= 0` are the same class: the body cannot be interpreted as a well-formed notification. Section 6 already maps that class to one stable code:

| Condition the model refuses | Code | Status | Authority |
| --- | --- | --- | --- |
| Extra field, missing required field, wrong type, empty `policy_number`, claim type not in §2.3, amount not `> 0` or not two decimal places, unparsable `loss_date` | `MALFORMED_REQUEST` | 400 | §2.4, §6 |

Invalid JSON is also 400 / `MALFORMED_REQUEST`, but that is the HTTP layer (Day 4), not the model. Section 5.2 already names it. The model does not see non-JSON.

Do **not** invent `UNKNOWN_FIELD`, `MISSING_FIELD`, `INVALID_CLAIM_TYPE` as separate codes unless the contract already split them. Adding many codes is compatible, but splitting what §2.4 treated as one class creates promises Day 4 then has to keep. One code for "caller's code is wrong" matches the split. Section 5.2's `problem` tokens (`value_not_in_vocabulary`, `invalid_scale`, …) are detail keys, not extra codes; mapping Pydantic error types onto them is Day 4.

On this branch section 6 already has `MALFORMED_REQUEST`. The reconciliation note therefore records that nothing was missing, and it shows how that was checked. Excellent reconciliation (15) requires the note to state **what was found, what was added, and how the check was performed**, not "section 6 is now complete." Adding nothing is the correct outcome when the inventory finds no gap.

**Method already used in the note (this is the Excellent bar):**

1. List every constraint declared on `NotificationRequest` and `Policy` (extra forbid, each required field, `min_length`, `Literal` claim types, `gt=0`, `decimal_places=2`, date parse, float rejection if present, Policy extras / date types / nullable cancellation).
2. For each constraint, name a payload that triggers it (the same cases as `test_models.py`).
3. Look up section 6 for a code and status for that refusal.
4. Record the gaps. Add the missing row(s) to section 6. (None on this branch.)
5. State explicitly that rule codes (`POLICY_NOT_FOUND`, `LOSS_BEFORE_INCEPTION`, …) are not produced by the models and were not in the scope of this check, so the note does not claim section 6 is exhaustive for the whole service.

**Acceptance criteria:** the reconciliation note exists, and every code the models can produce appears in contract section 6.

**Rubric:** Contract reconciliation (15). Excellent (15): every model rejection checked against §6, gaps closed with correct codes and statuses, note shows the method. Proficient (11): outcome recorded, method not visible. Developing (7): a gap closed but at least one model refusal still has no §6 entry. Inadequate (2): "nothing missing" with no evidence, or not attempted.

---

## 6. Out of scope today

From the assignment: `service.py` and the rule evaluation functions are Day 3, built test-first. `api/routes.py` is Day 4. Leave both as stubs.

Stop if you find yourself:

- Writing `if loss_date >= cancellation_date` anywhere.
- Raising or returning `POLICY_CANCELLED`, `DUPLICATE_NOTIFICATION`, `LOSS_BEFORE_INCEPTION`, or any other rule code from the repository or the models.
- Mapping `ValidationError` to an HTTP status in `models.py` or `repository.py`.
- Calling `find_matching` inside `record` and refusing to write.
- Accepting a `dict` in `record` or in any new helper outside `models.py`.
- Editing `policy_client.py`, the JSON under `data/`, or contract sections 1–3.
- Filling the entire Day 1 error envelope and dependency-failure mapping "while you are in section 6."

The boundary between deciding and doing is the thing you are practicing.

---

## 7. Files

### 7.1 Assignment deliverable (commit these on the feature branch)

| Path | Action |
| --- | --- |
| `src/claims/models.py` | Implement `NotificationRequest`, `Policy`, `RuleFailure`, `RecordedNotification` |
| `src/claims/repository.py` | Implement store, `issue_claim_reference`, `record`, `find_matching` |
| `tests/unit/test_models.py` | Add |
| `tests/unit/test_repository.py` | Add |
| `docs/payload-triage.md` | Reconciliation note already appended |
| `docs/api-contract.md` | Amend section 6 only if the inventory finds a missing model-produced code |

This plan file (`docs/w1-02-requirements-plan.md`) is not one of the four code files and is not the reconciliation note. Do not submit it as a substitute for the deliverable.

### 7.2 Supporting, only if needed

| Path | When |
| --- | --- |
| `tests/conftest.py` | Factory fixtures for fresh `NotificationRequest` / `NotificationRepository` |
| `pyproject.toml` | Pydantic mypy plugin if strict mypy cannot see model fields |

### 7.3 Do not edit

`src/claims/service.py`, `src/claims/api/routes.py`, `src/claims/policy_client.py`, `src/claims/api/__init__.py`, `data/*.json`, contract sections 1–3.

---

## 8. Acceptance criteria checklist

Each criterion is met or not met. There is no partial credit within a criterion. Map: AC → step that implements it → test that proves it → rubric cell it feeds.

| Acceptance criterion | Step | How you prove it | Rubric |
| --- | --- | --- | --- |
| `NotificationRequest` rejects a payload containing a field not in the model | 1, 5 | `extra="forbid"`; parametrized unknown-field case | Model spec 22; Test design 25 |
| Rejects a payload missing any required field, and no required field has a default | 1, 5 | Four missing-field cases; inspect defaults | Model spec 22 |
| `loss_date` is `date` and `estimated_amount` is `Decimal`, in both models; no date or money in source or tests is `str` or `float` | 1, 2, 3, 5, 6 | Types on `NotificationRequest`, `Policy`, `RecordedNotification`; tests construct with `date` / `Decimal` | Model spec 22 (Developing if money/date is unreliable) |
| `cancellation_date` typed so comparison without handling absence fails type checking | 2 | `date \| None` with no default; mypy would reject an unguarded `>=` | Model spec 22 Excellent (WI-0158 AC-3) |
| `RuleFailure` is immutable and carries rule identifier and error code as separate fields | 3, 5 | Frozen dataclass + `NewType`s; immutability test | Model spec; Code quality 20 |
| Repository returns a claim reference matching the contract format; no two records share a reference | 4, 6 | Format test; uniqueness test | Repository 18 |
| Duplicate detection matches on `policy_number`, `loss_date`, and `claim_type` together; two of three is not a duplicate | 4, 6 | `find_matching` plus three differing-field cases | Repository 18 |
| No rejected notification is recorded; a test shows resubmitting it is not a duplicate | 4, 6 | No reject-write API; AC-3 test never calls `record` then `find_matching` is `None` | Repository 18 Excellent (property of the design) |
| Every field constraint declared in either model has at least one violating test case | 5 | Constraint inventory ↔ parametrize rows | Test design 25 Excellent |
| Every test uses parametrization with named cases for multiple inputs; no loop over cases in a test body | 5, 6 | Review test files | Test design 25 |
| Every fixture returns a fresh object; full suite passes in any order | 5, 6 | Factories; `pytest` (and optionally `pytest --random-order` if available) | Test design 25 |
| `ruff check` and `mypy` exit zero; no suppression comment | 7 | Commands | Binary AC |
| No module outside `models.py` accepts a raw dictionary from a request payload | 1, 4 | `record(NotificationRequest)`; routes still stubbed | Model spec; Code quality |
| Reconciliation note exists; every code the models can produce appears in contract section 6 | 8 | Note shows method; §6 has `MALFORMED_REQUEST` (or equivalent) at 400 | Contract reconciliation 15 |

**Clarifications that prevent a false fail:**

- Assignment step 1's "422" for structural rejection is overridden by contract §2.4 (400). Models do not emit HTTP statuses.
- Assignment `ClaimRecord` is shipped as `RecordedNotification`. Do not rename it; `service.py` already imports the stub name.
- WI-0151 AC-2 (409, `DUPLICATE_NOTIFICATION`, `claim_reference` in detail) is not a Day 2 HTTP behaviour. Day 2 provides `find_matching` so Day 3 can implement AC-2 without teaching the repository about envelopes.
- WI-0158 AC-1, AC-2, AC-4 are not implemented as comparisons today. AC-3 is implemented as a type.

---

## 9. Rubric at a glance — what Excellent costs extra vs "it works"

| Cell | Points | The extra work beyond correctness |
| --- | --- | --- |
| Model specification | 22 | Types carry constraints (`Literal`, `date`, `Decimal`+`gt`+`decimal_places`, `extra=forbid`). `cancellation_date` is required-but-nullable. Every choice cites a contract line in a comment only when it would surprise. |
| Repository behavior | 18 | `issue_claim_reference`, `record`, and `find_matching` are separate. `record` always writes. AC-3 is "no reject API," not a flag. |
| Test design | 25 | Violating case per constraint. Ids readable in CI. Names in contract vocabulary. Deliberate INVALID/EDGE classification. Fresh fixtures. |
| Code quality | 20 | Contract words (`claim_reference`, `find_matching`, `policy_number`). No function whose honest name needs "and." Comments explain why and cite WI-0151 / WI-0158 / §2.4. |
| Contract reconciliation | 15 | Inventory → compare §6 → add gaps → note describes the method, including what was out of scope for the check. |

Total: 100. Each acceptance criterion is binary; the rubric is how well the design that met those criteria was done.

---

## 10. Suggested implementation order

When this document is used to implement, do the work in this order so tests can pin each boundary as you draw it:

1. Types and `NotificationRequest` in `models.py` (step 1).
2. `Policy`, `RuleFailure`, `RecordedNotification` (steps 2–3).
3. `test_models.py` including the payload classification parametrize (step 5). Fix model gaps the tests reveal.
4. Repository split into issue / record / find (step 4).
5. `test_repository.py` and factories (step 6).
6. `uv run pytest`, `ruff check`, `mypy` (step 7).
7. Constraint inventory against section 6; amend the contract only if a model-produced code is missing; write (or keep) the reconciliation note (step 8).

Do not start with the repository. The repository consumes `NotificationRequest` and `RecordedNotification`; those types have to exist and be strict first, or `record` will end up accepting a dict "for now."
