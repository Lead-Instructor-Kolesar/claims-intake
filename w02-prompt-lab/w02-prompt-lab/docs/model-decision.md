# Model Decision Record

Run ID: `day5-01`

Selection follows the committed Day 5 rule: triage prefers queue_accuracy, then escalation_accuracy, then fewer missed escalations, and disqualifies human-boundary or PII failures; summarization/extraction prefer required_evidence_recall, then citation_correctness, then unsupported_field_avoidance; ties break on median latency, then output tokens per case.

## Evaluated models

- mistral
- qwen

## Evidence rows

- `extraction` / mistral / `extract.v2`
- `extraction` / qwen / `extract.v2 (transfer)`
- `summarization` / mistral / `summarize.v1`
- `summarization` / qwen / `summarize.v1 (transfer)`
- `triage` / mistral / `triage.v1`
- `triage` / qwen / `triage.v1 (transfer)`

## Task decisions

### extraction

- selected model: mistral
- prompt version: `extract.v2`
- measured reason: highest required_evidence_recall (69/72), then citation_correctness (73/73), then unsupported_field_avoidance (8/12)
- rejected alternative(s): qwen/extract.v2 (transfer) (60/72)
- reopen when: a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this 12-case corpus

### summarization

- selected model: mistral
- prompt version: `summarize.v1`
- measured reason: highest required_evidence_recall (59/60), then citation_correctness (60/63), then unsupported_field_avoidance (8/12)
- rejected alternative(s): qwen/summarize.v1 (transfer) (55/60)
- reopen when: a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this 12-case corpus

### triage

- selected model: qwen
- prompt version: `triage.v1 (transfer)`
- measured reason: highest queue_accuracy (12/12), then escalation_accuracy (12/12), then fewer missed escalations (0/12)
- rejected alternative(s): mistral/triage.v1 (10/12)
- reopen when: a newer prompt version or model changes measured quality, latency, or boundary/PII outcomes on this 12-case corpus
