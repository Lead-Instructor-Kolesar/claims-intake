# Day 3 notes

- Summarization repair rate: 1/12
- Extraction repair rate: 0/12
- Example leakage count: 0
- Citation-existence failure count: 8

The most common validation error was a missing `EvidenceField.value` on fields already marked `status: "absent"`; Pydantic still requires `value`, even when it is `null`. The repair request sent that error back and the model filled `value: null` on those absent fields, which produced a valid `SummarizationOutput` on the single allowed retry.

All 24 cases ran under `run_id=1c82bf5f-71c4-44c0-ac37-015084709768` with `mistral:7b` at temperature `0.0`. Summarization used shipped `SummarizationOutput`; extraction used shipped `PolicyExtraction`. Citation checks read `EvidenceField.citation` against source section headings. Few-shot examples were `examples/superseded.md` and `examples/self-contradicting.md`.
