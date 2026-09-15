# Day 2 model comparison

Generated from `docs/day2-run.jsonl`. `cost_usd` is 0.0 for both configured models; this is not a dollar-cost race and no cost winner is named.

## mistral (`mistral:7b`)

- Attempts: 12
- Successes: 12
- Truncations: 0
- Other errors: 0
- Input tokens: sum=2775, mean=231.25
- Output tokens: sum=1319, mean=109.92
- Latency (ms): mean=4340.92, max=7673
- Latency median (ms): 3790.00
- cost_usd: 0.0

## qwen (`qwen3:8b`)

- Attempts: 12
- Successes: 12
- Truncations: 0
- Other errors: 0
- Input tokens: sum=2427, mean=202.25
- Output tokens: sum=4748, mean=395.67
- Latency (ms): mean=17252.00, max=23911
- Latency median (ms): 16752.00
- cost_usd: 0.0

## Observation

mistral succeeded on 12 of 12 attempts (truncations=0, other errors=0) with 2775 input tokens and 1319 output tokens; median latency 3790.00 ms, max 7673 ms. qwen succeeded on 12 of 12 attempts (truncations=0, other errors=0) with 2427 input tokens and 4748 output tokens; median latency 16752.00 ms, max 23911 ms. These counts and latencies come from the JSONL records; both models recorded cost_usd=0.0, so this is a token and latency comparison, not a dollar-cost ranking.
