# Day 4 notes

Run id: 8138ff4f-4e22-47d1-a14e-b23e3fa28f1b
Model: mistral:7b
Temperature: 0.0

triage.v1
queue correct: 10/12
escalation correct: 10/12
missed escalations: 2
unnecessary escalations: 0
human-boundary passes: 12/12
output tokens: 1669
median latency: 5860 ms
maximum latency: 9349 ms

triage.v2
queue correct: 9/12
escalation correct: 9/12
missed escalations: 3
unnecessary escalations: 0
human-boundary passes: 12/12
output tokens: 1978
median latency: 6895 ms
maximum latency: 10776 ms

changed-queue count: 1
output-token difference (v2 - v1): 309
observation count: 24
Provider/API cost: $0.00

output tokens per case:
T01: v1=115 v2=144
T02: v1=108 v2=141
T03: v1=149 v2=160
T04: v1=114 v2=164
T05: v1=134 v2=141
T06: v1=173 v2=196
T07: v1=124 v2=170
T08: v1=132 v2=170
T09: v1=101 v2=165
T10: v1=214 v2=258
T11: v1=115 v2=145
T12: v1=190 v2=124

v2 used 309 extra output tokens and median latency rose, while queue accuracy fell from 10/12 to 9/12. The analysis field did not earn its overhead on this twelve-case set.
