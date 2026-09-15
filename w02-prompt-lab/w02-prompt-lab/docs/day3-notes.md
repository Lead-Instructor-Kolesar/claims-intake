# Day 3 notes: prompts that return validated objects

Model: mistral:7b (logical name mistral), temperature 0.0, one run_id. Summarization ran prompts/summarize.v1.md over 12 summarization cases; extraction ran prompts/extract.v2.md over 12 extraction cases. A repair attempt means one bounded semantic repair request carrying the validation error; transport retries stay inside the adapter and are not counted.

## Metrics

- Summarization repair rate: 3/12 (25.0%)
- Extraction repair rate: 0/12 (0.0%)
- Example leakage count: 0 of 12 extraction outputs contained n-grams distinctive to the two few-shot example documents
- Citation-existence failures: 0 evidence fields with status "present" whose citation does not match a real section heading in the case source

## Most common validation error

The most common first-pass validation failure was the "1 validation error for SummarizationOutput\nrequired_steps.citation\n  Input should be a valid string [type=string_type, input_value=['3'], input_type=list]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type" error class, seen in 1 of 3 first attempts that failed validation.
The repair request repeated the delimited document together with the previous response and the validation error and asked the model to correct only that concern; this recovered 1 of 3 first-pass failures.
