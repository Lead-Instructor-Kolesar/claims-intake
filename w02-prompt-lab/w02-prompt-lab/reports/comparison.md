# Local Model Comparison

Run `day5-local-01` compared configured Ollama models. Local provider/API cost is `$0.00`.
Scorer `day5.v2`: required-evidence recall and citation correctness are extraction-only.
PII is scored on free-text fields (`draft_reply` / `rationale`, or extracted string values).
Qwen rows are prompt-transfer: the same Day 3/4 prompt versions, not Qwen-tuned variants.

## summarization

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs | Observations |
|---|---|---|---|---|---|---|---|---|
| mistral | summarize.v1 | status 8/12; PII 0/12; current-version 0/1 | 1106.1 | 321.8 | 12425 ms | 14778 ms | 2/12 | 14 |
| qwen | summarize.v1 transfer | status 10/12; PII 0/12; current-version 1/1 | 843.4 | 264.3 | 11796 ms | 15750 ms | 1/12 | 13 |

## extraction

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs | Observations |
|---|---|---|---|---|---|---|---|---|
| mistral | extract.v2 | required 72/72; citation 75/75; unsupported-avoided 15/18; PII 0/12 | 2102.9 | 387.5 | 18046 ms | 20634 ms | 0/12 | 12 |
| qwen | extract.v2 transfer | required 71/72; citation 73/73; unsupported-avoided 16/18; PII 0/12 | 1784.9 | 276.9 | 14525 ms | 18045 ms | 0/12 | 12 |

## triage

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs | Observations |
|---|---|---|---|---|---|---|---|---|
| mistral | triage.v1 | queue 10/12; escalation 9/12; missed 1/12; unnecessary 2/12; boundary 12/12; PII 0/12 | 822.8 | 140.1 | 5610 ms | 10484 ms | 0/12 | 12 |
| qwen | triage.v1 transfer | queue 11/12; escalation 8/12; missed 0/12; unnecessary 4/12; boundary 12/12; PII 0/12 | 699.6 | 117.4 | 5348 ms | 9012 ms | 0/12 | 12 |

## Limits

- There are only 12 cases per task.
  Results are directional, not production-scale estimates.
- Qwen rows are labeled prompt-transfer.
  No Qwen-adapted prompt version was introduced.
- Untested combinations: any prompt besides `summarize.v1`,
  `extract.v2`, and `triage.v1`; temperatures other than 0.0;
  models other than the two configured Ollama identities.
- No production-volume reliability claim is being made.
- Local Ollama latency depends on lab hardware.
- Do not treat an 11/12 vs 10/12 gap as a universal model ranking.
- Summarization is not scored on required-evidence recall or citation correctness.

## Recommendation

- **summarization**: model `qwen`, prompt `summarize.v1` transfer.
  Reason: document status 10/12 vs Mistral 8/12, schema-valid 12/12 vs 10/12,
  and `select_current_version` 1/1 vs 0/1 on this set. PII 0/12 both.
  Reopen if a Qwen-adapted prompt is recorded, or if Mistral schema failures on S05/S12 are fixed.
- **extraction**: model `mistral`, prompt `extract.v2`.
  Reason: required evidence 72/72 vs Qwen transfer 71/72, with citations 75/75 on present fields.
  The one-field gap is too small to rank models in general; Mistral is the model this prompt was developed against.
  Reopen if an `extract` prompt version tuned for Qwen is measured.
- **triage**: model `mistral`, prompt `triage.v1`.
  Reason: human boundary 12/12 and PII 0/12 on both models; Mistral escalation 9/12 with 2 unnecessary vs Qwen 8/12 with 4 unnecessary.
  Qwen transfer queued 11/12 vs 10/12, which is not enough to prefer it.
  Reopen if a later gold set weights queue accuracy over false escalations.
