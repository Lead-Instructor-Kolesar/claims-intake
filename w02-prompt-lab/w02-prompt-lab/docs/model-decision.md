# Model Decision Record

## evidence

- run_id: `day5-local-01`
- scorer_version: `day5.v2`
- provider: ollama; cost_usd: $0.00
- prompts: summarization=`summarize.v1`, extraction=`extract.v2`, triage=`triage.v1`
- Qwen used those exact versions as a prompt-transfer test
- models compared: mistral, qwen
- required-evidence recall and citation correctness scored on extraction only
- PII scored on free-text outputs with `PII_PATTERNS`; no LLM

## decision

- Summarization: `qwen` with `summarize.v1` transfer. Document status 10/12 vs Mistral 8/12; current-version rule 1/1 vs 0/1. Citations are not a summarization metric.
- Extraction: `mistral` with `extract.v2`. Required evidence 72/72 vs Qwen transfer 71/72; present-field citations 75/75 vs 73/73. Treat as directional, not a general extraction ranking.
- Triage: `mistral` with `triage.v1`. Human boundary 12/12 and PII 0/12 on both Mistral and Qwen. Do not prefer Qwen for an 11/12 vs 10/12 queue gap when it over-escalated more.

## rejected alternatives

- Inventing a cloud token price for local Ollama models
- Asking the model which policy version is current
  instead of `select_current_version`
- Scoring summarization with extraction required-evidence / citation metrics
- Switching triage to `triage.v2`; Day 4 showed the same 10/12
  queue with extra output tokens
- Treating Qwen transfer scores as proof that Qwen is worse at extraction in general

## review triggers

- A new gold case set larger than n=12
- A Qwen-adapted prompt version with its own recorded run
- Human-boundary failure on either model
- Material change to schema, adapter, or temperature
- A later scoring contract that scores summarization citations again
