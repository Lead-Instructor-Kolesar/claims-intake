# Day 2 local model comparison

Both models ran through Ollama with thinking disabled so the shared 256-token ceiling is spent on the answer. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1602
- Median latency_ms: 5278
- Max latency_ms: 8475

## qwen3:8b
- Successful cases: 12 / 12
- Input token total: 2487
- Output token total: 774
- Median latency_ms: 3009
- Max latency_ms: 7100

## Observation
mistral:7b completed 12/12 cases (no recorded errors) with 2679 input tokens, 1602 output tokens, median latency 5278 ms and max latency 8475 ms. qwen3:8b completed 12/12 cases (no recorded errors) with 2487 input tokens, 774 output tokens, median latency 3009 ms and max latency 7100 ms.
