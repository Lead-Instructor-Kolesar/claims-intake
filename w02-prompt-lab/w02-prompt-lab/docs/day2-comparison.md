# Day 2 model comparison

One `run_id` (`9760201e-f2a5-472a-9cef-fe49cbe74405`). Twelve summarization cases. Same prompt (`baseline` / `v0`), temperature `0.0`, and `max_output_tokens=1024`. Both models `provider="ollama"`. Local provider charge is `0.0` for every record; this comparison does not use dollar cost.

| Model | Success | Input tokens | Output tokens | Median latency | Max latency |
| --- | --- | --- | --- | --- | --- |
| `mistral:7b` | 12/12 | 2,679 | 1,602 | 5,916 ms | 10,415 ms |
| `qwen3:8b` | 12/12 | 2,355 | 5,352 | 19,520 ms | 46,066 ms |

Both models finished every case under the shared 1024 output-token ceiling (`stop_reason=stop`). Qwen still wrote about 3.3× as many output tokens and had a median latency about 3.3× Mistral’s on the same requests; the slowest call was Qwen S01 at 46,066 ms with 812 output tokens, so output length—not the input document—dominated this run’s workload.
