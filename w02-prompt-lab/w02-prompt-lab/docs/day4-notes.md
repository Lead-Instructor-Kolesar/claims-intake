# Day 4 notes: triage prompt comparison

Model: mistral:7b (logical name mistral), temperature 0.0, run_id d800b7fe-3fd2-41c6-aeb2-264e46629302. Both prompt versions ran all 12 triage cases through complete_structured. provider/API cost = $0.00; token and latency overhead are measured from local Ollama call records.

triage.v1: queue 9/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
triage.v2: queue 9/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
changed queue between versions: 0
output tokens/case: v1 = 143.5, v2 = 170.8, delta = +27.2
median latency: v1 = 6.80s, v2 = 8.07s
maximum latency: v1 = 10.63s, v2 = 10.37s
observation count: v1 = 12, v2 = 12
token figures include repair calls; repairs: v1 = 0, v2 = 0
analysis field order: schema_description lists analysis last, after queue, escalation_required, rationale, and draft_reply; sampled v2 analyses (T01, T02, T11) restated the already-chosen queue, and T08 named mixed profile-access plus takeover only after queue was already fraud_report.
conclusion: As implemented, the analysis field was generated after the routing fields and could not have influenced them; the overhead purchased a post-hoc justification. v2 reproduced every v1 routing decision verbatim (12/12) while adding 27.2 output tokens per case. Median latency moved 6.80s to 8.07s with that token delta; v2 max 10.37s stayed under v1 max 10.63s, so the overhead is a consistent median shift, not a tail risk. Ordering analysis first in the schema description is a v3 candidate, not Day 4 scope. The analysis field did not earn its overhead on this 12-case set with this model.
