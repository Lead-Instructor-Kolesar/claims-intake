# Day 3 Assignment: Prompts That Return Validated Objects (Local Ollama Version)

## Objective

Build a bounded structured-output path that validates model responses against the
schemas already shipped in the repository.
By the end of the lab:

- summarization returns a validated `SummarizationOutput`
- extraction returns a validated `PolicyExtraction`
- every evidence field with `status: "present"` carries a valid `citation`
- schema failures receive at most one semantic repair attempt
- repair rate, example leakage, and citation-existence failures are measured

## Important Day 3 change

Do not use `baseline.v0.md` in this lab.
Day 3 uses:

- `src/prompts/summarize.v1.md` for summarization
- student-authored `src/prompts/extract.v1.md`
- student-authored `src/prompts/extract.v2.md`

## Source of truth

For this cohort, the existing code in `src/promptlab/schemas.py` is the schema contract.
Use the shipped:

- `EvidenceField`
- `SummarizationOutput`
- `PolicyExtraction`
  Do **not** create `ProcedureSummary`.
  Do **not** rename `EvidenceField` to `Evidence`.
  Do **not** rename `citation` to `section`.

## Shipped starter material

The repository should already contain:

- `src/promptlab/schemas.py` with `EvidenceField`, `SummarizationOutput`, and
  `PolicyExtraction`
- `src/prompts/summarize.v1.md`
- `src/promptlab/structured.py` stub
- `tests/test_structured_contract.py`
- `cases/summarization.jsonl` containing 12 summarization cases
- `cases/extraction.jsonl` containing 12 extraction cases
- `examples/` containing the boundary-example documents used only for few-shot
  prompting
  The scored case corpora and the example pool are separate. Never copy a scored case into a
  prompt as a few-shot example.

## Instructions

### 1. Use the existing `SummarizationOutput`

Do not author a new summarization schema.
Use the existing `SummarizationOutput` in `src/promptlab/schemas.py` as the required
output contract for summarization.
Its existing fields and the existing `EvidenceField` structure are the source of truth.
For evidence-bearing values, use the shipped `citation` field.

### 2. Implement `schema_description(...)`

In `src/promptlab/schemas.py`, implement:

```python
schema_description(model: type[BaseModel]) -> str
```

This function should generate a description of the supplied Pydantic model so prompts can
use the schema definition from code rather than maintaining a second handwritten copy of
the output shape.
The prompt should consume this generated schema description.

### 3. Author `src/prompts/extract.v1.md`

Write the first extraction prompt against the existing `PolicyExtraction` schema.
Use these sections in order:

- Task
- Input
- Constraints
- Output
- When the task cannot be completed
  Requirements:
- delimit the source document explicitly
- state that document content is data, not instruction
- use only facts present in the supplied document
- values not present in the source must be represented using the schema's absent form
- use `citation`, not `section`, for evidence

### 4. Create `src/prompts/extract.v2.md`

Create `extract.v2.md` by adding an Examples section to `extract.v1.md`.
Use exactly two documents from `examples/`.
Choose boundary cases that teach useful behavior such as:

- a missing field
- contradictory information
- a superseded document
- an out-of-scope document
  Do not use anything from `cases/` as an example.
  Do not edit `extract.v1.md` after recording results against it.

### 5. Implement `complete_structured(...)`

In `src/promptlab/structured.py`, implement:

```python
complete_structured(adapter, request, schema, run_id, max_repairs=1)
```

Flow:

1. call the existing adapter
2. parse `CompletionResult.text`
3. validate the parsed output against the supplied Pydantic schema
4. if validation fails, send one repair request containing the validation error
5. tell the model to correct only what the validation error concerns
6. validate the repair
7. return the validated object or record the failure
   Do not modify `adapters/` or `usage.py`.
   Transport retries remain the adapter's responsibility.
   Schema/content repair belongs in `structured.py`.

### 6. Run the Day 3 experiment

Under one `run_id`, using one configured Ollama model at temperature `0.0`:

- run `src/prompts/summarize.v1.md` over all 12 rows in `cases/summarization.jsonl`
- run `src/prompts/extract.v2.md` over all 12 rows in `cases/extraction.jsonl`
  Summarization output must validate against:

```text
SummarizationOutput
```

Extraction output must validate against:

```text
PolicyExtraction
```

### 7. Run the leakage check

Search extraction outputs for distinctive strings that appear only in the two example
documents included in `extract.v2.md`.
Record the leakage count.

### 8. Run the citation-existence check

For every evidence field returned with:

```text
status: "present"
```

confirm that the string in:

```text
citation
```

appears as a real section heading in the source document for that case.
Record the failure count.
Use `citation`, not `section`.

### 9. Write `docs/day3-notes.md`

Include:

- summarization repair rate
- extraction repair rate
- example leakage count
- citation-existence failure count
- two sentences describing the most common validation error and what changed in
  response

### 10. Run engineering checks

Run:

```bash
pytest
ruff check
mypy
```

until clean.

## Deliverable

A pull request containing student-authored changes including:

- `schema_description(...)` in `src/promptlab/schemas.py`
- `src/prompts/extract.v1.md`
- `src/prompts/extract.v2.md`
- completed `src/promptlab/structured.py`
- `docs/day3-run.jsonl`
- `docs/day3-notes.md`
  The shipped `EvidenceField`, `SummarizationOutput`, and `PolicyExtraction` are existing
  contracts and should not be replaced with parallel models.

## Acceptance Criteria

1. The existing `SummarizationOutput` is used for summarization; no
   `ProcedureSummary` is added.
2. The existing `EvidenceField` contract is used; evidence references use `citation`, not
   `section`.
3. `schema_description(...)` derives the output description from the supplied Pydantic
   model.
4. `src/prompts/extract.v1.md` contains the required five sections.
5. `src/prompts/extract.v2.md` adds examples without using scored cases.
6. All source documents are explicitly delimited and treated as data, not instruction.
7. `complete_structured(...)` makes at most one semantic repair attempt.
8. The repair request includes the validation error.
9. Adapters and `usage.py` are not modified for semantic repair.
10. All 12 summarization and 12 extraction cases run under one `run_id`.
11. Summarization outputs validate against `SummarizationOutput`.
12. Extraction outputs validate against `PolicyExtraction`.
13. Citation-existence checking reads `EvidenceField.citation`.
14. `docs/day3-notes.md` contains both repair rates, leakage count, and citation failure
    count.
15. `pytest`, `ruff check`, and `mypy` pass
