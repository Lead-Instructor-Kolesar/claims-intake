# Day 2 local model comparison

Both models ran through Ollama at the default thinking setting with a shared 1024-token ceiling. Local provider/API charge is 0.0; this note does not invent a cloud price.

## mistral:7b
- Successful cases: 12 / 12
- Input token total: 2679
- Output token total: 1602
- Median latency_ms: 5270
- Max latency_ms: 8569

## qwen3:8b
- Successful cases: 12 / 12
- Input token total: 2415
- Output token total: 5442
- Median latency_ms: 19318
- Max latency_ms: 44179

## Observation
mistral:7b completed 12/12 cases (no recorded errors) with 2679 input tokens, 1602 output tokens, median latency 5270 ms and max latency 8569 ms. qwen3:8b completed 12/12 cases (no recorded errors) with 2415 input tokens, 5442 output tokens, median latency 19318 ms and max latency 44179 ms.
