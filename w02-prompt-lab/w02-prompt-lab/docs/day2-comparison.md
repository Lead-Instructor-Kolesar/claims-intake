# Day 2 local model comparison

Both models ran through Ollama at the default thinking setting with a shared 512-token ceiling. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1602
- Median latency_ms: 5281
- Max latency_ms: 8520

## qwen3:8b
- Successful cases: 10 / 12
- Input token total: 2415
- Output token total: 5036
- Median latency_ms: 19621
- Max latency_ms: 25630

## Observation
mistral:7b completed 12/12 cases (no recorded errors) with 2679 input tokens, 1602 output tokens, median latency 5281 ms and max latency 8520 ms. qwen3:8b completed 10/12 cases (errors TruncatedResponseError=2) with 2415 input tokens, 5036 output tokens, median latency 19621 ms and max latency 25630 ms.
