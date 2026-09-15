# Day 4 notes

Run id: aabf4f45-897b-4748-b8cf-c2f063366343
Model: mistral:7b
Temperature: 0.0

triage.v1
queue correct: 10/12
escalation correct: 10/12
missed escalations: 2
unnecessary escalations: 0
human-boundary passes: 12/12
output tokens: 1661
median latency: 5604 ms
maximum latency: 10568 ms

triage.v2
queue correct: 8/12
escalation correct: 9/12
missed escalations: 3
unnecessary escalations: 0
human-boundary passes: 12/12
output tokens: 1792
median latency: 6669 ms
maximum latency: 9848 ms

changed-queue count: 2
output-token difference (v2 - v1): 131
observation count: 24
Provider/API cost: $0.00

output tokens per case:
T01: v1=154 v2=135
T02: v1=128 v2=129
T03: v1=140 v2=143
T04: v1=116 v2=134
T05: v1=130 v2=126
T06: v1=130 v2=164
T07: v1=153 v2=150
T08: v1=122 v2=147
T09: v1=116 v2=154
T10: v1=228 v2=225
T11: v1=107 v2=124
T12: v1=137 v2=161

v2 used 131 extra output tokens and median latency rose, while queue accuracy fell from 10/12 to 8/12. The analysis field did not earn its overhead on this twelve-case set.
