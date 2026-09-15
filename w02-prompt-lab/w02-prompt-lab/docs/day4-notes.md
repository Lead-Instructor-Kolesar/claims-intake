# Day 4 notes

One `run_id` (`12b075fc-79d0-4e84-a92b-b9f81eebbd36`). One model (`mistral:7b`). Temperature `0.0`. Same 12 triage cases and the same `max_output_tokens=1024` for both prompts. Local provider/API cost is `$0.00`.

## triage.v1

- queue correct: 9/12
- escalation correct: 7/12
- missed escalations: 0
- unnecessary escalations: 5
- human-boundary passes: 12/12

## triage.v2

- queue correct: 9/12
- escalation correct: 7/12
- missed escalations: 0
- unnecessary escalations: 5
- human-boundary passes: 12/12

## Comparison

- changed-queue count: 1 (T08: `fraud_report` → `account_servicing`; gold is `escalate`)
- output tokens: v1 1,794 across 13 observations; v2 1,960 across 12 observations; difference v2 − v1 = +166
- median latency: v1 7,107 ms; v2 8,789.5 ms
- maximum latency: v1 11,573 ms; v2 10,759 ms
- observation count: v1 13 (T08 used one schema repair); v2 12

Output tokens by case (v1 → v2): T01 134→164, T02 128→146, T03 137→171, T04 131→147, T05 131→180, T06 120→164, T07 200→201, T08 253→166, T09 129→153, T10 165→123, T11 119→171, T12 147→174.

T06, T07, and T08 stayed off the gold `escalate` queue on both versions. Five clear cases still set `escalation_required` when gold did not.

The extra `analysis` field did not improve queue or escalation scores. One queue change in a 12-case set is not evidence that v2 is better. The added output tokens and higher median latency were not earned.
