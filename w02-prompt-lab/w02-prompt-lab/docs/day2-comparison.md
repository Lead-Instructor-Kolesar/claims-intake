# Day 2 model comparison

Run id: 2b1f164c-f29d-47de-b8ff-c651b9a196e9
12 summarization cases ran through baseline v0 at temperature 0, with a max output of 1024 tokens.
Both models used provider ollama and are distinguished by the configured model id.
Every recorded cost_usd is 0.0. Local Ollama has no per-token provider charge, so this note does not compare dollar cost.

## mistral:7b

- successes: 12
- attempts: 12
- failures: 0
- truncations: 0
- input tokens: 2775
- output tokens: 1318
- median latency: 4236 ms
- max latency: 9997 ms

## qwen3:8b

- successes: 12
- attempts: 12
- failures: 0
- truncations: 0
- input tokens: 2487
- output tokens: 5633
- median latency: 21707 ms
- max latency: 38342 ms

## Observation

qwen3:8b used 4.3 times the output tokens of mistral:7b and 5.1 times the median latency on the same twelve cases. Input tokens stayed close (2775 vs 2487), so the extra wall time tracks longer generation rather than a billed API. That gap also fits how qwen3:8b keeps thinking on by default in Ollama. We never set a think flag in the adapter, but the model still spends tokens on internal reasoning before the final answer, which shows up as higher output counts and slower median latency.
