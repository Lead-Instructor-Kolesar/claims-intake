# Day 1 Assignment: Instrumenting a Local Model Call

## Objective

Instrument a real local model call end to end and produce a usage record that later work can read. By the end, each call records what model ran, which case and prompt were used, token counts, latency, stop reason, error state, response text, and local provider charge in an append-only JSONL file.

This version uses **Mistral through Ollama** instead of a commercial cloud API. Day 1 uses one model. A later model-comparison exercise can introduce Qwen through the same local Ollama service.

## Prerequisites

- The Week 2 repository is cloned and the devcontainer is running.
- Ollama is installed and running on the host Mac.
- On the host Mac, run `ollama pull mistral:7b` and `ollama pull qwen3:8b` if the models are not already installed.
- Inside the devcontainer, `curl http://host.docker.internal:11434/api/tags` returns the installed models.
- `uv sync --frozen` has completed.

## Shipped in the starter material

Do not retype these files. They are supplied in the repository.

- The existing `src/promptlab/config.py`, which contains the Ollama base URL and configured Mistral/Qwen model identifiers.
- `prompts/baseline.v0.md`, the supplied Day 1 baseline prompt.
- `cases/extraction.jsonl`, the supplied extraction corpus.
- `scripts/raw_call_example.py`, a minimal working Ollama call showing where response text, input-token count, output-token count, and stop reason appear.
- `src/promptlab/errors.py`, containing `UnknownModelError`.
- `tests/test_usage_contract.py`, which checks the Day 1 record contract without making a model call.

## The contract

Implement `CallRecord` as a Pydantic v2 model in `src/promptlab/usage.py` with exactly these twenty fields:

| Field | Type | Notes |
| --- | --- | --- |
| `record_id` | `str` | UUID4 generated per record |
| `run_id` | `str` | identifies one execution |
| `timestamp` | `datetime` | timezone-aware UTC |
| `provider` | `Literal["ollama"]` | this local assignment uses Ollama |
| `model_id` | `str` | read from configuration, never hardcoded at the call site |
| `task` | `Literal["triage", "summarization", "extraction"]` | Day 1 uses `extraction` |
| `case_id` | `str` | e.g. `E12` |
| `prompt_id` | `str` | `baseline` |
| `prompt_version` | `str` | `v0` |
| `attempt` | `int` | 1 for the first attempt |
| `temperature` | `float` | the value actually sent |
| `max_output_tokens` | `int` | maps to Ollama `num_predict` |
| `input_tokens` | `int` | Ollama `prompt_eval_count` |
| `output_tokens` | `int` | Ollama `eval_count` |
| `cached_input_tokens` | `int | None` | use `None` for this lab |
| `latency_ms` | `int` | measured around the HTTP call |
| `cost_usd` | `float` | local provider charge; derived from configuration |
| `stop_reason` | `str | None` | Ollama `done_reason` when available |
| `error_type` | `str | None` | `None` on success |
| `response_text` | `str | None` | returned model text |

Records append to `runs/{run_id}.jsonl`, one JSON object per line. A run file is never rewritten or edited in place.

### Local cost semantics

Ollama running on the student's machine has no per-token API/provider fee. The configured provider charge for Mistral and Qwen is therefore `$0.00`. Keep `cost_usd` in the record so the instrumentation contract remains useful, but do not invent a cloud price for a local model.

`compute_cost(model_id, input_tokens, output_tokens)` must still reject an unknown model identifier by raising `UnknownModelError` rather than silently returning zero.

## Instructions

1. Implement `CallRecord` in `src/promptlab/usage.py` exactly as specified above.
2. Implement `compute_cost(model_id, input_tokens, output_tokens)`. Use the model configuration already present in the repository. A configured local model returns a provider charge of `0.0`; an unknown model raises `UnknownModelError`.
3. Implement `append_record(record, run_id)` so it creates `runs/` when necessary and appends one JSON object per line to `runs/{run_id}.jsonl`.
4. Read `scripts/raw_call_example.py` and identify the Ollama fields used for response text, input tokens, output tokens, and stop reason.
5. Write `src/promptlab/day1.py` with a `main()` that reads `cases/extraction.jsonl` and selects cases `E12`, `E07`, and `E11`. These give you a shorter, middle-sized, and longer input from the supplied corpus.
6. Load `prompts/baseline.v0.md`, replace `{document_text}` with each case's `source`, and call the configured **Mistral** model at temperature `0.0`.
7. Measure latency around each model call. Map `prompt_eval_count` to `input_tokens`, `eval_count` to `output_tokens`, and `done_reason` to `stop_reason`.
8. Generate a UUID4 `record_id`, use a timezone-aware UTC timestamp, create one `CallRecord` for each successful call, and append it under one `run_id`.
9. Make one deliberate extra call against `E11` with a very small `num_predict` value. If Ollama reports `done_reason="length"`, record that attempt with `error_type="TruncatedResponseError"`. Restore the normal output ceiling afterward. Do not include this demonstration attempt in the final three-record evidence file.
10. Run `uv run pytest tests/test_usage_contract.py`, `uv run ruff check src/promptlab/usage.py src/promptlab/day1.py`, and `uv run mypy src/promptlab/usage.py src/promptlab/day1.py` until clean.
11. Copy the three successful Day 1 records to `docs/day1-run.jsonl`.
12. Write `docs/day1-observations.md` in no more than three sentences. Compare the shortest and longest cases by input-token count and latency, then state what that tells you about estimating model workload from only a short document.

## Deliverable

A merge request containing:

- `src/promptlab/usage.py`
- `src/promptlab/day1.py`
- `docs/day1-run.jsonl` with exactly three successful records
- `docs/day1-observations.md`

## Acceptance criteria

1. `CallRecord` has exactly the twenty fields above with the specified names and types.
2. `tests/test_usage_contract.py` passes unmodified and without network access.
3. The Day 1 script makes real local Ollama calls to the configured Mistral model.
4. Model identifiers are read from configuration rather than duplicated at the call site.
5. Every successful record captures Ollama's reported input and output token counts.
6. Every timestamp is timezone-aware and in UTC.
7. Records are appended to JSONL rather than overwriting the run file.
8. An unknown model identifier raises `UnknownModelError`.
9. The deliberate low-output call is detected as truncation when Ollama reports the output ceiling was reached.
10. No cloud credentials are required and no populated `.env` file is committed.
11. `pytest`, `ruff`, and `mypy` are clean for the Day 1 work.
12. `docs/day1-observations.md` contains the requested comparison in no more than three sentences.
