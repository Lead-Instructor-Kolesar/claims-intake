# Day 4 notes: triage prompt comparison

Model: mistral:7b (logical name mistral), temperature 0.0, run_id e7a4efd0-1ba3-44a8-a6d6-87d131ff32fb. Both prompt versions ran all 12 triage cases through complete_structured. provider/API cost = $0.00; token and latency overhead are measured from local Ollama call records.

triage.v1: queue 9/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
triage.v2: queue 10/12, escalation 10/12, missed 1, unnecessary 1, boundary 12/12
changed queue between versions: 1
output tokens/case: v1 = 143.5, v2 = 174.2, delta = +30.8
median latency: v1 = 6.62s, v2 = 7.78s
maximum latency: v1 = 12.16s, v2 = 9.76s
observation count: v1 = 12, v2 = 12
conclusion: v2 spent extra output tokens and queue accuracy moved by one case; a one-case difference on 12 cases is a shrug, not a verdict, so the analysis field did not earn its overhead.
