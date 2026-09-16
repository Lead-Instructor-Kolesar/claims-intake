# Model Decision Record

## evidence

- run_id: `day5-local-01`
- provider: ollama; cost_usd: $0.00
- prompts: summarization=`summarize.v1`, extraction=`extract.v2`, triage=`triage.v1`
- Qwen used those exact versions as a prompt-transfer test
- models compared: mistral, qwen

## decision

- Summarization: `qwen` with `summarize.v1` transfer. Citations matched source headings (60/60) while Mistral was 0/60 on this 12-case set.
- Extraction: `mistral` with `extract.v2`. Required evidence 72/73 vs Qwen transfer 71/73; treat as directional, not a general extraction ranking.
- Triage: `mistral` with `triage.v1`. Human boundary 12/12 and PII 0/12 on both Mistral and Qwen. Do not prefer Qwen for an 11/12 vs 10/12 queue gap when it over-escalated more.


## rejected alternatives

- Inventing a cloud token price for local Ollama models
- Asking the model which policy version is current
  instead of `select_current_version`
- Switching triage to `triage.v2`; Day 4 showed the same 10/12
  queue with extra output tokens
- Treating Qwen transfer scores as proof that Qwen is worse at extraction in general

## review triggers

- A new gold case set larger than n=12
- A Qwen-adapted prompt version with its own recorded run
- Human-boundary failure on either model
- Material change to schema, adapter, or temperature
