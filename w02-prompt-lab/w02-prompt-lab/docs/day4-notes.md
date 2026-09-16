# Day 4 notes

- Model: `mistral:7b` at temperature `0.0`, one `run_id=bf381570-c405-4abb-9327-e14ea1561314`
- Observation count: 24 CallRecords in `runs/bf381570-c405-4abb-9327-e14ea1561314.jsonl`
- Cost: `$0.00` (local Ollama)

## v1 (TriageOutput, no analysis)
- Queue: 10/12
- Escalation: 9/12
- Missed escalation: 1/12
- Unnecessary escalation: 2/12
- Human boundary: 12/12
- Output tokens: 1681; median latency 6898 ms; max latency 8687 ms

## v2 (TriageOutputWithAnalysis)
- Queue: 10/12
- Escalation: 9/12
- Missed escalation: 1/12
- Unnecessary escalation: 2/12
- Human boundary: 12/12
- Output tokens: 1770; median latency 7472 ms; max latency 8607 ms

## v1 vs v2
- Changed-queue count: 1/12 (T06: `fraud_report` → `card_dispute`; gold is `escalate`)
- Output-token delta (v2 - v1): 89
- Same error pattern on both versions: queue misses T06 and T07; missed escalation T07; unnecessary escalation T02 and T12

v2's analysis field did not earn the extra output tokens or latency: queue accuracy is unchanged at 10/12, and a one-case queue swap is too small to treat as a real gain.
