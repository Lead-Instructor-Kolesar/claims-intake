# Week 2 carryover: what you import and how to call it

`src/promptlab/` is Week 2's code. Week 3 imports it in place and modifies
nothing in it. You read about all of this in Week 2. This page is the call shape,
so you are not reconstructing an API from an article while trying to write a
retrieval system.

This is reference for supplied code. It is not a tutorial and it does not explain
why any of it is shaped this way; the Week 2 articles do that.

## The eight things Week 3 uses

### `complete_structured`

Calls a model and parses the response into a Pydantic model, with one repair
attempt carrying the validation error.

```python
from promptlab.adapters.anthropic import AnthropicAdapter
from promptlab.adapters.base import CompletionRequest
from promptlab.structured import complete_structured

outcome = complete_structured(
    adapter=AnthropicAdapter(),
    request=CompletionRequest(
        task="extract",
        case_id="q07",
        prompt_id="answer",
        prompt_version="v1",
        system=template.system,
        user_content=rendered,
        temperature=0.0,
        max_output_tokens=2048,
    ),
    schema=GroundedAnswerDraft,
    run_id=run_id,
)

if outcome.succeeded:
    draft = outcome.parsed          # a validated GroundedAnswerDraft
else:
    outcome.error_type              # "ValidationError", or a provider error
    outcome.error_detail            # the validation message
outcome.repairs_used                # 0 or 1
outcome.records                     # one CallRecord per attempt, in order
```

A failure is returned, not raised. Record it rather than discarding it.

### `schema_description`

Produces the text a prompt uses to describe its required output. Prompts call
this instead of restating the structure, so the schema stays the only definition.

```python
from promptlab.schemas import schema_description

contract = schema_description(GroundedAnswerDraft)
```

Put the result into the output section of your prompt. Do not also describe the
structure in prose; that creates a second source of truth and the two will
disagree.

### The prompt registry

```python
from promptlab.prompts import load, render_user
from rag.config import PROMPT_DIR

template = load("answer", "v1", PROMPT_DIR)   # src/rag/prompts/answer.v1.md
rendered = render_user(
    template,
    variables={"question": question, "as_of": str(filters.as_of)},
    untrusted=evidence_block_text,
)
```

`render_user` escapes the closing marker inside `untrusted` and raises
`MissingPromptVariableError` when a placeholder has no value. `{document_text}` is
supplied automatically from the `untrusted` argument; every other placeholder
comes from `variables`.

A prompt file carries its system message in front matter:

```
---
system: |
  You are answering a compliance analyst's question about applicable policy.
---
Question: {question}
Review date: {as_of}

<document>
{document_text}
</document>
```

A prompt that produced a recorded result is never edited. A change is a new
version file.

### `select_current_version`

Decides which revision of each document is in force at a date. There is one
implementation of this rule and it is here.

```python
from promptlab.rules import select_current_version

current = select_current_version(candidates, as_of)   # {"kyc-ie-0004": "v4.2"}
```

`candidates` is any sequence of objects carrying `doc_id`, `version`,
`effective_date`, and `superseded_by`. Week 3 projects `DocumentMeta` onto that
shape in `rag/versioning.py`. Do not write a date comparison anywhere in
`src/rag/`.

### `ScoreRecord`, `MetricResult`, and `Metric`

```python
from promptlab.scoring import Metric, MetricResult, ScoreRecord
```

A metric takes the parsed output and the gold object and returns one
`MetricResult` per field it examined. Week 3 wraps `ScoreRecord` in
`StageScoreRecord` rather than changing it, so a Week 2 record and a Week 3
record still validate against the same model.

Every result carries `scorer_version`. Increment it when a metric changes, and
land that change in a commit containing nothing else.

### `CallRecord` and spend

Every model call writes a `CallRecord` through the adapter, including failed
attempts and repairs. You do not write records yourself for completions; the
adapter does it. You do write them for embeddings, which is Day 1's work, and
`EmbeddingCallRecord` follows the same shape.

The ceiling is checked before a call is made and raises `BudgetExceededError`
rather than warning. The running total spans `runs/completions/` and
`runs/embeddings/`.

```python
from rag.spend import check_budget
check_budget(run_id, projected_usd=estimated)
```

## Two things that trip people up

**Positions, not identifiers.** Week 3 asks the model to cite `[4]`, and code
resolves that to a `chunk_id` through the block record. Never ask the model to
reproduce a `chunk_id`. A well-formed identifier naming a version that does not
exist passes every check you could write; a position outside the block range
fails arithmetically.

**Two schemas, not one.** `GroundedAnswerDraft` is what the model returns and
contains only fields a model can supply. `GroundedAnswer` is what you store and
adds `chunk_ids`, `plan_id`, `block_id`, and `evidence_incomplete`, all populated
by code. A field the model cannot answer honestly is a field it will answer
anyway.
