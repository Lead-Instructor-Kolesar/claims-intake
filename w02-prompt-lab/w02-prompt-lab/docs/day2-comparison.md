# Day 2 local model comparison

Both models ran through Ollama. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1539
- Median latency_ms: 5022
- Max latency_ms: 8061

## qwen3:8b
- Successful cases: 12 / 12
- Input token total: 2487
- Output token total: 774
- Median latency_ms: 3060
- Max latency_ms: 7070

## Observation
mistral:7b completed 12/12 cases (no recorded errors) with 2679 input tokens, 1539 output tokens, median latency 5022 ms and max latency 8061 ms. qwen3:8b completed 12/12 cases (no recorded errors) with 2487 input tokens, 774 output tokens, median latency 3060 ms and max latency 7070 ms.
