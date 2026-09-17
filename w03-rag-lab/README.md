# w03-rag-lab

Week 3 of the Associate FDE training program: retrieval-augmented generation over
a versioned policy corpus.

By the end of the week this repository answers a compliance analyst's question
about applicable policy with cited sections at a stated as-of date, or declines
with a reason, and reports per stage where every failing question was lost.

## Getting started

Everything runs in the devcontainer. Open the folder in a container and the
toolchain, the dependencies, and the Postgres service come up together. There is
no installation step in any assignment this week.

```
cp .env.example .env      # populate with the credentials issued to you
uv sync
uv run pytest
```

`.env` is ignored and never enters a commit. Connection details for the store
come from the environment, which the devcontainer sets.

## The contract tests fail. That is intended.

Seven tests fail on a fresh clone. They pin the interfaces the week's assignments
produce, and they turn green as the work lands:

- `tests/test_corpus_contract.py` passes once `chunk_document` exists (Day 1).
- `tests/test_lineage_contract.py` passes once `IngestionRecord` exists (Day 5).

Everything else is green from the first hour and stays green. If a test outside
those two files fails, something is wrong with the environment rather than with
your work.

## Layout

```
migrations/          Day 1 schema, applied at container start
migrations/day5/     document table and the chunk foreign key, applied on Day 5
src/promptlab/       Week 2, carried in place and not modified this week
src/rag/             Week 3
src/rag/prompts/     prompt files, versioned, never edited after a recorded run
corpus/source/       the policy corpus, 30 documents
corpus/source-b/     the same 30 documents re-exported, used on Day 5
corpus/manifest.json every source file with its SHA-256
cases/questions/     the scored analyst questions
cases/gold/          gold labels, supplied on Day 4
examples/questions/  development questions, answers visible, never scored
runs/                record streams, gitignored
docs/                what you commit as evidence
tools/               corpus generator, build-time only
reports/             the evaluation report
```

Two conventions worth knowing before you trip over them.

`src/promptlab/prompts.py` sits beside `src/promptlab/prompts/`, and the same
pattern repeats under `src/rag/`. Python resolves this in favor of the module only
while the directory is not a package. Do not add an `__init__.py` to a prompts
directory; it breaks every import.

`migrations/day5/` is staged deliberately. `003_document.sql` adds a foreign key
from `chunk` to `document`, and ingestion does not write document rows until
Day 5. Applying it earlier fails every chunk insert. Day 5 setup runs
`STAGE=day5 bash .devcontainer/apply-migrations.sh`.

## What is shipped and what you write

Shipped complete, and not modified by any assignment: `config.py`, `store.py`,
`spend.py`, `tokens.py`, `fusion.py`, `parse_labeled_header`, every migration,
every model marked as shipped in its module docstring, and all of
`src/promptlab/`.

Everything else carries a docstring naming the day and the instruction that
produces it, and raises `NotImplementedError` until you write it.

## Coming from Week 2

`src/promptlab/` is Week 2's code, carried in place. You read about it in Week 2
and Week 3 asks you to use it rather than rebuild it.
`docs/week2-carryover.md` is the call shape for the eight things Week 3 imports:
`complete_structured`, `schema_description`, the prompt registry,
`select_current_version`, `ScoreRecord`, `MetricResult`, `Metric`, and
`CallRecord`. Read it before Day 1.

Reimplementing any of them inside `src/rag/` costs marks in the Week 3 lab rubric
and puts two definitions of one rule in the repository.

## The corpus

Thirty synthetic policy documents in three families, with version chains, two
jurisdictions, three entity types, and two header conventions. Twenty-four case
questions with no visible answers, four example questions with their expected
chunks, and gold labels supplied on Day 4.

`tools/build_corpus.py` regenerates all of it. `tests/test_corpus_data.py` pins
what the corpus must contain, so a regeneration that breaks a deliverable fails
the suite rather than the classroom.

None of it is real client data and none of it is the Coforge capstone package.

## Switching generation provider

Week 3 uses one generation model. Day 1 does not use it at all, because Day 1 is
embeddings only and embeddings are Azure.

To switch, change `GENERATION_PROVIDER` and `GENERATION_MODEL` together in
`src/rag/config.py`:

```python
GENERATION_PROVIDER = "azure_openai"
GENERATION_MODEL = "gpt-5-mini"
```

Nothing else changes. `rag.models.generation_adapter()` is the only place an
adapter is constructed, and a test fails if the two constants disagree. Call
`generation_adapter()` rather than instantiating an adapter yourself.

## Budget

Twenty US dollars for the week, two US dollars per run, enforced in
`rag.spend.check_budget` before a call is made rather than reported after. The
running total spans completion records and embedding records, because ingestion
embeds the whole corpus and a rebuild does it again.

Verify the rates in `config.PRICING_USD_PER_MTOK` against current provider
pricing before quoting any cost figure in a report.
