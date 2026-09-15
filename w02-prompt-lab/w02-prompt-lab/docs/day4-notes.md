# Day 4 notes: triage prompt comparison

Model: mistral:7b (logical name mistral), temperature 0.0, run_id d800b7fe-3fd2-41c6-aeb2-264e46629302. Both prompt versions ran all 12 triage cases through complete_structured. provider/API cost = $0.00; token and latency overhead are measured from local Ollama call records.

triage.v1: queue 9/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
triage.v2: queue 9/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
changed queue between versions: 0
output tokens/case: v1 = 143.5, v2 = 170.8, delta = +27.2
median latency: v1 = 6.80s, v2 = 8.07s
maximum latency: v1 = 10.63s, v2 = 10.37s
observation count: v1 = 12, v2 = 12
conclusion: v2 spent extra output tokens without changing queue accuracy on this 12-case set, so the analysis field did not earn its overhead.
