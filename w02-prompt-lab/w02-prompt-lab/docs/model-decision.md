# Model decision record

Run: `3f34c708-0e48-42a9-862f-c016ccaa451d`. Scorer: `day5.v1`. Temperature `0.0`. Provider `ollama`. Cost `$0.00`. Adapter: `/api/generate` with `think: false`. Evidence files: `docs/day5-run.jsonl`, `docs/day5-scores.jsonl`, `reports/comparison.md`.

Constraints frozen before this comparison (not rewritten after seeing scores):

- Task prompts stay `summarize.v1`, `extract.v2`, `triage.v1`.
- Qwen runs those files as transfer tests. No Day 5 prompt retune.
- Day 4 already rejected `triage.v2` on Mistral (same 9/12 queue and 7/12 escalation, more output tokens).
- `baseline.v0` is historical. `extract.v3` was not the Day 5 extraction prompt.
- Metrics are deterministic counts with denominators. No LLM-as-judge. No invented cloud prices.

## Evidence

| Task | Model | Prompt | What was measured |
|---|---|---|---|
| summarization | Mistral | `summarize.v1` | document_status 7/12; required evidence 50/60; missed 10/60; unsupported 2/52; citations 52/52; PII 0/60; version selection 1/1; repairs 2/12 (S04, S09 extra `appendix_table`); median 15,211 ms (n=14); max 19,139 ms (n=14) |
| summarization | Qwen | `summarize.v1` transfer | document_status 9/12; required evidence 60/60; missed 0/60; unsupported 4/64; citations 64/64; PII 0/72; version selection 1/1; repairs 0/12; median 13,382 ms (n=12); max 20,502 ms (n=12) |
| extraction | Mistral | `extract.v2` | document_status 8/12; required evidence 68/72; missed 4/72; unsupported 4/72; citations 72/72; PII 0/84; version selection 1/1; repairs 0/12; median 20,223.5 ms (n=12); max 25,197 ms (n=12) |
| extraction | Qwen | `extract.v2` transfer | document_status 9/12; required evidence 71/72; missed 1/72; unsupported 2/73; citations 73/73; PII 0/84; version selection 1/1; repairs 0/12; median 15,936 ms (n=12); max 20,551 ms (n=12) |
| triage | Mistral | `triage.v1` | queue 9/12; escalation 7/12; missed 0/12; unnecessary 5/12; human boundary 12/12; PII 0/24; repairs 1/12 (T08); median 5,415 ms (n=13); max 7,965 ms (n=13) |
| triage | Qwen | `triage.v1` transfer | queue 10/12; escalation 8/12; missed 0/12; unnecessary 4/12; human boundary 12/12; PII 0/24; repairs 0/12; median 5,557.5 ms (n=12); max 9,141 ms (n=12) |

Human boundary was checked on both models. Sample size is 12 cases per task.

## Decision

For this lab, use **Qwen** with the transferred Day 5 prompts and thinking disabled:

- summarization → Qwen + `summarize.v1`
- extraction → Qwen + `extract.v2`
- triage → Qwen + `triage.v1`

Mistral remains the model the prompts were developed on. The Qwen scores are transfer scores on a 12-case set, not a claim that Qwen is generally better.

## Rejected alternatives

- **Mistral + `summarize.v1` as the lab default.** Lower status (7/12) and two schema failures on the appendix-table trap (S04, S09). Keep as the prompt-authoring model.
- **Mistral + `extract.v2` as the lab default.** Validated 12/12, but 68/72 recall vs Qwen transfer 71/72 on the same prompt.
- **Mistral + `triage.v1` as the lab default.** Matches Day 4 (9/12 queue, 7/12 escalation, 12/12 boundary). Qwen transfer was 10/12 and 8/12 with the same boundary. Not a large gap; not enough to prefer Mistral once transfer is labeled.
- **`triage.v2`.** Day 4: same quality, +166 output tokens, higher median latency. Not selected then; not rerun on Qwen.
- **`extract.v3` / `baseline.v0`.** Not the Day 5 task prompts.
- **Qwen with thinking on.** That run truncated: 22/52 Qwen calls `TruncatedResponseError`, empty `response` on mixed/escalate triage. It measured token budget, not task quality. Not used for this decision.

## Review triggers

Reopen this record if any of the following happens:

- The case set grows beyond 12 per task, or gold labels change.
- A new prompt version is introduced (`summarize.v2`, Qwen-adapted extraction, or a return to `triage.v2`).
- `think` is enabled, `max_output_tokens` changes, or temperature is not 0.0.
- Human-boundary or PII leakage is non-zero on a committed `draft_reply`.
- Version selection misses S02 or E02 after a clean extraction.
- Schema repair rate on Qwen stops being 0/12, or Mistral extra-key failures spread beyond S04/S09.
