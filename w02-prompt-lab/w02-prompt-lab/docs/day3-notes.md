# Day 3 notes

One `run_id` (`5159746b-6db6-49c2-a2c4-1eb98ff67e13`). One model (`mistral:7b`). Temperature `0.0`. Prompts: `summarize.v1.md` and `extract.v2.md`. Local cost is `0.0`.

- Summarization repair rate: 2/12 (0.17)
- Extraction repair rate: 2/12 (0.17)
- Example leakage count: 0
- Citation-existence failure count: 1

The most common validation error was extra_field (4 first-pass case(s)). The repair request now includes that Pydantic error text and tells the model to correct only those fields, then re-validates the JSON.
