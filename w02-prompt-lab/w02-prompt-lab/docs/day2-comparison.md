# Day 2 local model comparison

Both models ran through Ollama. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1602
- Median latency_ms: 5507
- Max latency_ms: 10331

## qwen3:8b
- Successful cases: 0 / 12
- Input token total: 2415
- Output token total: 3072
- Median latency_ms: 12058
- Max latency_ms: 14229

## Observation
mistral:7b completed 12/12 cases (no recorded errors) with 2679 input tokens, 1602 output tokens, median latency 5507 ms and max latency 10331 ms. qwen3:8b completed 0/12 cases (errors TruncatedResponseError=12) with 2415 input tokens, 3072 output tokens, median latency 12058 ms and max latency 14229 ms.
