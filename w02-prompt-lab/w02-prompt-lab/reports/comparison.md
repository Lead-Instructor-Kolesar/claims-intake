# Model Comparison

Run ID: `day5-01`

Counts are reported with their denominators. Latency uses median and maximum rather than mean. Local Ollama provider/API charge is `$0.00`.

## Extraction

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | n | Repairs | Retries | Failures |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mistral | extract.v2 | citation_correctness: 73/73<br>document_status_accuracy: 9/12<br>missing_required_evidence: 3/72 ↓<br>pii_leakage: 0/12 ↓<br>required_evidence_recall: 69/72<br>unsupported_field_avoidance: 8/12<br>unsupported_field_invention: 4/12 ↓<br>version_selection_accuracy: 1/1 | 2027.9 | 389.9 | 35756.5 ms | 48333 ms | 12 | 0 | 0 | 0 |
| qwen | extract.v2 (transfer) | citation_correctness: 62/74<br>document_status_accuracy: 9/12<br>missing_required_evidence: 0/72 ↓<br>pii_leakage: 0/12 ↓<br>required_evidence_recall: 60/72<br>unsupported_field_avoidance: 8/12<br>unsupported_field_invention: 2/12 ↓<br>version_selection_accuracy: 1/1 | 1675.9 | 1446.1 | 138450 ms | 180005 ms | 13 | 0 | 1 | 2 |

## Summarization

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | n | Repairs | Retries | Failures |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mistral | summarize.v1 | citation_correctness: 60/63<br>document_status_accuracy: 9/12<br>missing_required_evidence: 1/60 ↓<br>pii_leakage: 0/12 ↓<br>required_evidence_recall: 59/60<br>unsupported_field_avoidance: 8/12<br>unsupported_field_invention: 4/12 ↓<br>version_selection_accuracy: 1/1 | 1365.2 | 301.8 | 25276.5 ms | 36057 ms | 12 | 0 | 0 | 0 |
| qwen | summarize.v1 (transfer) | citation_correctness: 56/61<br>document_status_accuracy: 11/12<br>missing_required_evidence: 0/60 ↓<br>pii_leakage: 0/12 ↓<br>required_evidence_recall: 55/60<br>unsupported_field_avoidance: 10/12<br>unsupported_field_invention: 1/12 ↓<br>version_selection_accuracy: 1/1 | 1130.2 | 835.2 | 62794 ms | 180009 ms | 13 | 0 | 1 | 1 |

## Triage

| Model | Prompt | Quality | Input tokens/case | Output tokens/case | Median latency | Max latency | n | Repairs | Retries | Failures |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mistral | triage.v1 | escalation_accuracy: 10/12<br>human_boundary_compliance: 12/12<br>missed_escalation: 2/12 ↓<br>pii_leakage: 0/12 ↓<br>queue_accuracy: 10/12<br>unnecessary_escalation: 0/12 ↓ | 1135.8 | 139.1 | 11437.5 ms | 24451 ms | 12 | 0 | 0 | 0 |
| qwen | triage.v1 (transfer) | escalation_accuracy: 12/12<br>human_boundary_compliance: 12/12<br>missed_escalation: 0/12 ↓<br>pii_leakage: 0/12 ↓<br>queue_accuracy: 12/12<br>unnecessary_escalation: 0/12 ↓ | 953.6 | 488.1 | 46356 ms | 58782 ms | 12 | 0 | 0 | 0 |

## Recommendation

- `extraction`: **mistral** with `extract.v2` because highest required_evidence_recall (69/72), then citation_correctness (73/73), then unsupported_field_avoidance (8/12); no generation failures. Reopen if a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this corpus.
- `summarization`: **mistral** with `summarize.v1` because highest required_evidence_recall (59/60), then citation_correctness (60/63), then unsupported_field_avoidance (8/12); no generation failures. Reopen if a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this corpus.
- `triage`: **qwen** with `triage.v1 (transfer)` because highest queue_accuracy (12/12), then escalation_accuracy (12/12), then fewer missed escalations (0/12); no generation failures. Reopen if a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this corpus.

## Human boundary

Draft replies were checked for customer-outcome language under both evaluated models (`mistral`, `qwen`).
A configuration with any human-boundary failure or PII leak is disqualified from selection.

## Limits

- Each task uses a fixed 12-case sample; treat counts as lab evidence, not production-scale precision.
- Transfer rows reuse prompts developed on the home model; they are not proof of the best adapted prompt for the transferred model.
- Untested combinations (other prompt versions, temperatures, or models) are out of scope for this run.
- Latency and throughput depend on local hardware and Ollama runtime state.
- Both models used a shared max_output_tokens of 2048.
- 3 evaluations produced no validated output (including truncated generations) and were scored as zeros; those rows affect recall ranking.
- This report does not claim production readiness or invent a dollar cost comparison; local provider charge remains `$0.00`.
