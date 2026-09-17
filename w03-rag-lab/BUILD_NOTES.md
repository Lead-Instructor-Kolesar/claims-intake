# w03-rag-lab build notes

Written for whoever finishes and runs this repository. It records what is built,
what is not, the decisions taken while building, and the defects found in the
shipped Week 3 content along the way.

## Status

**Built and verified.** The repository scaffolding, the devcontainer and its
Postgres service, CI, all four migrations, `src/rag/` with every shipped model and
every stub, all of `src/promptlab/`, thirty corpus documents plus thirty in the
second export, twenty-four case questions, twenty-four gold labels, four example
questions, both manifests, `docs/week2-carryover.md`, and nine test files.

`ruff check` passes. Fifty-six tests pass and seven fail by design, as described
below.

**Still to do before handover.** Four things, in order of risk.

1. Nobody has built the container. The compose file, the pgvector image, the
   migration script, and the CI service block are all first-draft and have never
   been run. Open the folder in a container once and apply the migrations before
   fifteen people do.
2. Confirm an Azure embeddings deployment of `text-embedding-3-small` is
   available in the cohort's region and subscription. Day 1 is entirely embedding
   work and does not start without it. This also settles the unverified 0.02 per
   million rate.
3. Generate and commit `uv.lock` with `uv lock`.
4. Anthropic Console API keys are still open. This does not block the week; see
   below.

**Anthropic is not a blocker.** Day 1 is embeddings only and uses Azure. Days 2
through 5 need one generation model, pinned as `claude-sonnet-5` but switchable
to `gpt-5-mini` by changing `GENERATION_PROVIDER` and `GENERATION_MODEL` together
in `src/rag/config.py`. `rag.models.generation_adapter()` is the only place an
adapter is constructed and a test fails if the two constants disagree, so the
switch is genuinely two lines. `gpt-5-mini` will rerank less well on Day 4 and
fail schema validation more often on Day 3, and neither hurts the teaching: Day 4
measures per-stage attribution rather than absolute quality, and a visible repair
rate on Day 3 is what the article tells them to track.

## The seven failing tests are intentional

`tests/test_corpus_contract.py` (five) and `tests/test_lineage_contract.py` (two)
pin interfaces that Day 1 and Day 5 produce. They fail on a fresh clone and turn
green as the work lands. This follows the Week 1 convention of shipping contract
tests that fail until the work is done.

Every other test passes from the first hour. CI on the starter branch is
therefore red, deliberately, and goes green on the first merged assignment.

## src/promptlab/ needs reconciling

Week 3 is seeded from a reference implementation of the Week 2 end state. That
reference implementation was never built. It was item six on the list of blockers
raised in September and it never got an owner.

What is here was authored against the surface the Week 2 articles specify, not
copied from an existing build. Where the articles print code verbatim, that code
is reproduced exactly: `FieldStatus`, `Evidence`, `PolicyExtraction`,
`MetricResult`, `ScoreRecord`, `Metric`, `PromptTemplate`, `load`, `render_user`,
`MARKER_OPEN`, and `MARKER_CLOSE`. Where the articles specify behavior without
printing code, it was written to that specification: `CallRecord` and its field
table, `compute_cost`, `append_record`, the error taxonomy, the adapter protocol
with its retry and budget policy, `complete_structured` with its single capped
repair, `schema_description`, and `select_current_version`.

Week 2's assignments were created on the fly during delivery and produced no
competing `promptlab`, so there is nothing to reconcile against and this is the
only implementation. `tests/test_week2_surface.py` pins the surface Week 3
imports, so if another build does turn up it produces a specific difference list
rather than a vague sense that something moved.

The cohort read the Week 2 articles but never called this code.
`docs/week2-carryover.md` gives the call shape for the eight things Week 3
imports. It is reference for supplied code, not teaching content, so it does not
step on Week 2.

Three lint rules are scoped off for two promptlab files in `pyproject.toml`. They
would restyle code Associates read verbatim in Week 2 and hold in their own
repositories. Nothing under `src/rag/` is exempt.

## Defects found in the shipped Week 3 content

**Migration 003 breaks Day 1.** `003_document.sql` adds a foreign key from `chunk`
to `document`, and ingestion does not write document rows until Day 5. Applied at
container start, it fails every chunk insert from Day 1 onward. It is staged into
`migrations/day5/` and applied by `STAGE=day5 bash .devcontainer/apply-migrations.sh`.
The Day 5 lab brief says this migration ships "already applied", which is now
satisfied by that command rather than by the container start. Worth correcting in
the brief.

**Day 2 acceptance criterion 11 is not substring-checkable.** The criterion is that
no `query_text` contains a jurisdiction code. Checked naively, the code `IE`
matches inside ordinary English words including "review", so a compliant query
reports a violation. The check has to be word-boundary matched, which
`tests/test_retrieval_contract.py` demonstrates. Worth adding to the criterion.

## Decisions taken while building

**Embedding model.** `text-embedding-3-small` at 1536 dimensions, pinned in
`rag/config.py`. The deployment name is read from
`AZURE_OPENAI_EMBEDDING_DEPLOYMENT` because Associates create their own Azure
deployments. Confirm the model against what Coforge provisions.

**Generation model.** `claude-sonnet-5`, pinned, with `gpt-5-mini` available
through the second adapter. Week 3 does not repeat Week 2's model comparison, so
no deliverable requires the second provider for completions.

**Pricing.** Sonnet 5 at 2.00 and 10.00 US dollars per million tokens, gpt-5-mini
at 0.25 and 2.00, carried from the Week 2 confirmation.
`text-embedding-3-small` at 0.02 per million input tokens is **unverified** and
must be checked before any cost figure is quoted.

**Spend.** Twenty US dollars for the week and two per run, per the Week 3 plan.
Week 2's own ceiling of twenty-five stays in `promptlab/config.py` so that carried
Week 2 code behaves as it did. `SPEND_RECORD_DIRS` spans completions and
embeddings, which is the one change to the Week 2 end state and is documented in
that file.

**The vector column literal.** `001_chunk.sql` ships with `vector(1536)` and the
comment the article prints, rather than a templated value, so the migration reads
as SQL and matches the article. `tests/test_schema_guard.py` asserts the literal
equals `EMBEDDING_DIMENSION`, so the two cannot drift apart silently.

**No `uv.lock`.** It has to be generated by `uv lock` with network access from the
target platform. Every dependency is pinned to an exact version in
`pyproject.toml` and every compiled package was confirmed to have a cp312
manylinux aarch64 wheel: `psycopg-binary` 3.3.5, `pydantic-core` 2.49.0,
`tiktoken` 0.14.0, and `numpy` 2.5.3. Nothing compiles from source in the
container. Generate and commit the lock file before handover.

**`select_current_version` takes a protocol.** Week 2 supplies extracted fields and
Week 3 supplies parsed ingest metadata. Both project onto four attributes, which
is what lets one rule serve both without a second implementation. `rag/versioning.py`
owns the projection and owns no date logic, and its docstring says so.

## The corpus

Generated by `tools/build_corpus.py` and pinned by `tests/test_corpus_data.py`,
which fails the suite rather than the classroom if a regeneration breaks a
deliverable.

**Thirty documents.** Twelve KYC periodic review policies, ten card dispute
procedures, eight compliance manual documents. Two jurisdictions, three entity
types, version chains of one to three revisions, numbered sections throughout.
Twenty-two use the labeled header and eight use a document control table, which
is Day 1's parser dispatch. Section text varies by version, jurisdiction, and
entity type, so no two documents are byte-identical except where a defect
intends it. Every section fits inside `CHUNK_MAX_CHARS`, so every gold chunk
identifier ends in ordinal zero.

**Four planted defects.**

`cmp-ie-0021 v1.4` and `cmp-uk-0041 v3.1` carry an effective date written without
a day number. No reader can parse it, so it stays null in every build. This is
the count Day 1 asks for.

`cdp-uk-0014 v1.3` is the same content as `cdp-uk-0002 v1.3` under a second
identifier, exported without the supersession link. Detected by grouping
`document` on `source_sha256`, which is the Day 5 article's worked example.

`kyc-uk-0019 v2.3` has a body byte-identical to `v2.2`.

`cdp-uk-0021 v3.0` section 3.2 carries a note addressed to whoever is reading the
document, instructing it to report that no evidence is needed. Retrieved as an
ordinary chunk on question `q11`.

**`corpus-b`.** `corpus/source-b/` is the same thirty documents re-exported from a
different system, where three KYC Ireland documents write the effective date as
`01 November 2025` rather than in ISO form. A Day 1 parser returns null for those
three. Because the currency rule cannot place an undated revision in the chain,
`kyc-ie-0004` resolves to `v3.1` and `kyc-ie-0007` to `v1.0`, both withdrawn.
`v3.1` states the documentation threshold as 10 percent where `v4.2` states 25,
so the wrong answer is materially wrong rather than cosmetically. Nine of the
twenty-four case questions are affected and no others.

This is deliberately not a second loader. The Associate builds `corpus-b` with
their own ingestion, diagnoses it, fixes their parser, rebuilds, and compares.
That matches the lab's requirement that the fix land in the loader and be
evidenced by a build comparison, and it means there is no legacy loader source
sitting in the repository that hands over the answer on inspection.

Day 1's nulls and `corpus-b`'s nulls are deliberately different. Day 1's have no
day number and are irreducible. `corpus-b`'s parse once the reader handles the
format, which is why the fix belongs in the loader.

**Questions.** Twenty-four cases, eighteen answerable and six abstentions, with
all four abstention reasons exercised: an out-of-scope subject, a record question
about a named customer, a jurisdiction the corpus does not cover, two questions
where the corpus is silent on the value asked for, and one where two in-force
documents disagree. `q03` and `q04` are the same question either side of an
effective date, with different correct answers. Case questions ship with no
visible answer; the four example questions ship with their expected chunks, for
Day 3's diagnostic probes.

## Decisions I made rather than asking

**Gold labels ship in the repository from Day 1**, in `cases/gold/`, rather than
being withheld until Day 4 as the Week 3 plan proposed. Withholding them means
shipping the repository twice, and the honest control is the rubric rather than
file availability. If you want them withheld, delete `cases/gold/` from the
Associate copy and ship it on Day 4; nothing else changes.

**The corpus is BFS only**, per the curriculum, so the FNOL use case is not
rehearsed against its own material this week.

**Provisional credit thresholds carry a currency** and registries and regulators
are named per jurisdiction. This is what makes documents distinguishable to a
retriever, and it was a real defect on the first build: without it, ten KYC
documents had byte-identical bodies and the gold labels were ambiguous.
