# Local Model Comparison

Run `day5-local-01` compared configured Ollama models. Local provider/API cost is `$0.00`.
Qwen rows are prompt-transfer: the same Day 3/4 prompt versions, not Qwen-tuned variants.

## summarization

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs | Observations |
|---|---|---|---|---|---|---|---|---|
| mistral | summarize.v1 | required 58/60; citation 0/60 | 1106.1 | 321.8 | 12425 ms | 14778 ms | 2/12 | 14 |
| qwen | summarize.v1 transfer | required 60/60; citation 60/60 | 843.4 | 264.3 | 11796 ms | 15750 ms | 1/12 | 13 |

## extraction

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | Repairs | Observations |
|---|---|---|---|---|---|---|---|---|
| mistral | extract.v2 | required 72/73; citation 72/73; unsupported-avoided 15/18 | 2102.9 | 387.5 | 18046 ms | 20634 ms | 0/12 | 12 |
| qwen | extract.v2 transfer | required 71/73; citation 71/72; unsupported-avoided 16/18 | 1784.9 | 276.9 | 14525 ms | 18045 ms | 0/12 | 12 |

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

## Recommendation

- **summarization**: model `qwen`, prompt `summarize.v1` transfer.
  Reason: required evidence 60/60 vs Mistral 58/60, and citations 60/60 vs Mistral 0/60 on this set.
  Reopen if a Qwen-adapted prompt is recorded, or if Mistral citations are fixed without dropping recall.
- **extraction**: model `mistral`, prompt `extract.v2`.
  Reason: required evidence 72/73 vs Qwen transfer 71/73, with citations 72/73.
  The one-field gap is too small to rank models in general; Mistral is the model this prompt was developed against.
  Reopen if an `extract` prompt version tuned for Qwen is measured.
- **triage**: model `mistral`, prompt `triage.v1`.
  Reason: human boundary 12/12 and PII 0/12 on both models; Mistral escalation 9/12 with 2 unnecessary vs Qwen 8/12 with 4 unnecessary.
  Qwen transfer queued 11/12 vs 10/12, which is not enough to prefer it.
  Reopen if a later gold set weights queue accuracy over false escalations.

