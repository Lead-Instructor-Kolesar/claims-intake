# Day 4 notes: triage prompt comparison

Model: mistral:7b (logical name mistral), temperature 0.0, run_id e7a4efd0-1ba3-44a8-a6d6-87d131ff32fb. Both prompt versions ran all 12 triage cases through complete_structured. provider/API cost = $0.00; token and latency overhead are measured from local Ollama call records.

triage.v1
queue correct: 9/12
escalation correct: 10/12
missed escalations: 1
unnecessary escalations: 1
human-boundary passes: 12/12

triage.v2
queue correct: 10/12
escalation correct: 10/12
missed escalations: 1
unnecessary escalations: 1
human-boundary passes: 12/12

changed queue between versions: 1 (T08 moved from fraud_report to escalate, the mixed profile-access plus takeover case)
output tokens/case: v1 = 143.5, v2 = 174.2, token difference = +30.8
median latency: v1 = 6.62s, v2 = 7.78s
maximum latency: v1 = 12.16s, v2 = 9.76s
observation count: v1 = 12, v2 = 12
token figures include repair calls; repairs: v1 = 0, v2 = 0
analysis field order: schema_description lists analysis before queue and the other routing fields, and triage.v2.md asks the model to write analysis first, so the field is generated before the queue is chosen; the ordering is the variable under test in this comparison.
ordering history: the earlier recording of this comparison (run d800b7fe, kept on the submitted Day 4 branch) listed analysis last, so the field was generated after the queue and could only restate it; its sampled v2 analyses restated the already-chosen queue and T05 duplicated its rationale verbatim. This run re-records both versions with the ordering reversed.
confidence drift: v2 raised confidence on 3 of 12 cases (T01, T05, T10: 0.95 to 1.0) and lowered it on 3 (T06: 0.9 to 0.8; T07: 0.95 to 0.9; T08: 0.9 to 0.8); the lowerings land on the mixed or missed cases, the direction a human reviewer would want. Confidence is not a scored metric; reported from run evidence.
draft-quality note (not a boundary failure): "[Your Company Name]" placeholder appears in the v1 T10 draft; the contracted boundary check over draft_reply and customer_outcome stays 12/12.
statistical resolution: 1 discordant pair in 12 paired cases leaves the sign test uninformative; this run cannot establish that analysis-first routing is better, only that the ordering determines whether the analysis field can influence routing at all.
conclusion: a one-case queue difference on 12 cases is a shrug, not a verdict; the +30.8 output tokens per case and +1.16s median latency bought one corrected routing, exactly the mixed-signals case a post-hoc analysis field could only describe. At this resolution the analysis field's overhead is not yet earned, and the ordering change is what makes the question measurable.
