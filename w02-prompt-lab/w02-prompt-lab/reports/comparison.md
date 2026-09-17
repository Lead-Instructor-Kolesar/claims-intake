# Local model comparison (Day 5)

One `run_id` (`3f34c708-0e48-42a9-862f-c016ccaa451d`). Temperature `0.0`. `max_output_tokens=1024`. Both models `provider="ollama"`. Configured IDs: `MODEL_A` / `MODEL_B` (this run: `mistral:7b`, `qwen3:8b`). Local provider cost is `$0.00` on every call. Do not read these rows as a dollar comparison.

Prompts (frozen; not edited after this run):

| Task | Prompt | Schema |
|---|---|---|
| summarization | `summarize.v1` | `SummarizationOutput` |
| extraction | `extract.v2` | `PolicyExtraction` |
| triage | `triage.v1` (Day 4 selected version) | `TriageOutput` |

All three prompts were written while working with Mistral. Every Qwen row is a **prompt-transfer** result: the same file on the second model, not a Qwen-tuned prompt.

Adapter note: `/api/generate` sent top-level `think: false`. That is a runtime flag, not a prompt version. A prior Qwen run with thinking left on spent the 1024-token cap on hidden reasoning (`TruncatedResponseError` 22/52 Qwen calls). This comparison uses the no-think run only.

Scorer: `day5.v1`. No metric calls a model.

- Required-evidence recall: gold `recoverable_fields` vs fields with `status="present"`.
- Citation correctness: for each present field, the citation string must appear in the source (empty citations fail). Headings are not parsed separately.
- Personal-data leakage: `PII_PATTERNS` on applicable free text (triage `rationale` / `draft_reply`; evidence field values and citations).
- Version currency: `select_current_version` on extracted dates, not a model opinion.

Latency is median and maximum of **CallRecord** observations, not a mean, not case-averaged. Token /case figures are totals divided by 12 cases (repair attempts are included in the totals).

## Summarization (`summarize.v1`)

Headline quality: `document_status` vs gold `expected_status`.

| Model | Prompt | Quality | Required evidence | Missed | Unsupported | Citations | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral | `summarize.v1` | 7/12 | 50/60 | 10/60 | 2/52 | 52/52 | 1,470 | 332 | 15,211 ms (n=14) | 19,139 ms (n=14) | 2/12 |
| Qwen | `summarize.v1` transfer | 9/12 | 60/60 | 0/60 | 4/64 | 64/64 | 1,040 | 247 | 13,382 ms (n=12) | 20,502 ms (n=12) | 0/12 |

Version selection (`card-dispute-intake`, as of 2025-06-01): Mistral 1/1, Qwen 1/1 (selected S02). PII leakage: Mistral 0/60, Qwen 0/72.

Mistral S04 and S09 failed schema after one repair. Both documents have a fifth heading, `5. Appendix Table`, that conflicts with the body. Gold wants `contradictory`. Mistral added an extra key `appendix_table`; the repair set that key to `null`; `extra="forbid"` rejects the key either way. Qwen did not emit that key. That is schema discipline on a designed trap, not a thinking-token failure.

## Extraction (`extract.v2`)

Headline quality: `document_status`. Missed and unsupported stay separate.

| Model | Prompt | Quality | Required evidence | Missed | Unsupported | Citations | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral | `extract.v2` | 8/12 | 68/72 | 4/72 | 4/72 | 72/72 | 1,875 | 387 | 20,223.5 ms (n=12) | 25,197 ms (n=12) | 0/12 |
| Qwen | `extract.v2` transfer | 9/12 | 71/72 | 1/72 | 2/73 | 73/73 | 1,615 | 277 | 15,936 ms (n=12) | 20,551 ms (n=12) | 0/12 |

Version selection (`small-business-periodic-kyc`, as of 2025-06-01): Mistral 1/1, Qwen 1/1 (selected E02). PII leakage: Mistral 0/84, Qwen 0/84. All 12×2 extraction cases validated.

Do not read the Qwen extraction row as “Qwen is better at extraction.” It is Qwen running Mistral’s `extract.v2`.

## Triage (`triage.v1`)

| Model | Prompt | Queue | Escalation | Missed | Unnecessary | Human boundary | PII | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral | `triage.v1` | 9/12 | 7/12 | 0/12 | 5/12 | 12/12 | 0/24 | 694 | 150 | 5,415 ms (n=13) | 7,965 ms (n=13) | 1/12 |
| Qwen | `triage.v1` transfer | 10/12 | 8/12 | 0/12 | 4/12 | 12/12 | 0/24 | 533 | 120 | 5,557.5 ms (n=12) | 9,141 ms (n=12) | 0/12 |

Human-boundary check was run on **both** Mistral and Qwen. No validated `draft_reply` promised a refund, approved or denied a claim, or stated a final customer outcome. Mistral T08 used one schema repair and then validated.

Day 4 compared `triage.v1` vs `triage.v2` on Mistral only: both 9/12 queue and 7/12 escalation; v2 added tokens and latency. Day 5 therefore kept `triage.v1`. `triage.v2` was not rerun on Qwen.

## Local measurements

| | Mistral | Qwen |
|---|---|---|
| Provider | ollama | ollama |
| Cost | $0.00 | $0.00 |
| Call records | 39 | 36 |
| Schema repairs (cases with a second `complete`) | 3/36 | 0/36 |
| Final schema failures | 2/36 (S04, S09) | 0/36 |
| Truncations (`done_reason=length`) | 0 | 0 |
| Transport retries | 0 | 0 |

Total observations in this run: 75 CallRecords for 72 task/model/case slots. Across both models that is 2/72 final schema failures.

## Limits

- 12 cases per task. Counts are directional. 10/12 vs 9/12 is not a production-scale ranking and is not a universal model ranking.
- Qwen rows are prompt-transfer rows. Untested here: `triage.v2` on Qwen, `extract.v3`, `summarize.v2`, temperature other than 0.0, `think: true`.
- No production-volume reliability claim is being made.
- Local Ollama latency depends on this lab machine. Median/max are for this hardware, this run, with thinking disabled.
- Citation scoring checks that the citation substring appears in the source; it does not require an exact heading match.
- `baseline.v0.md` remains Day 1–2 history and was not a Day 5 task prompt.

## Recommendation

| Task | Model | Prompt | Reason | Reopen if |
|---|---|---|---|---|
| summarization | Qwen | `summarize.v1` transfer | 9/12 status and 60/60 recall; Mistral lost S04/S09 to an extra `appendix_table` key | A `summarize.v2` that forbids extra keys is measured, or thinking is turned back on |
| extraction | Qwen | `extract.v2` transfer | 9/12 status, 71/72 recall, 1 missed vs Mistral’s 4, 0 repairs | Recall or unsupported fields move on a set larger than 12, or a Qwen-adapted prompt is introduced |
| triage | Qwen | `triage.v1` transfer | 10/12 queue, 8/12 escalation, 0 missed, 12/12 boundary, 0 PII; v1 already beat v2 on Mistral in Day 4 | Mixed `escalate` gold cases (T06–T08) are retested on a larger set, or boundary/PII fails |

Use Qwen on these three frozen prompts under `think: false` for this lab. Keep Mistral as the development model of record for the prompt files themselves. Revisit if any review trigger in `docs/model-decision.md` fires.
