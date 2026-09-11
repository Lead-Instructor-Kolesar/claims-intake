# Day 2 local model comparison

Both models ran through Ollama. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1602
- Median latency_ms: 4948
- Max latency_ms: 8305

## qwen3:8b
- Successful cases: 0 / 12
- Input token total: 2415
- Output token total: 3072
- Median latency_ms: 10952
- Max latency_ms: 13227

## Observation
mistral:7b completed 12/12 cases (none=12) with 2679 input tokens, 1602 output tokens, median latency 4948 ms and max latency 8305 ms. qwen3:8b completed 0/12 cases (TruncatedResponseError=12) with 2415 input tokens, 3072 output tokens, median latency 10952 ms and max latency 13227 ms.
