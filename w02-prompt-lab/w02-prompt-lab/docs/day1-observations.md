# Day 1 observations

The shortest case (E12) used 228 input tokens and finished in 2284 ms; the longest (E11) used 274 input tokens and took 4827 ms. That is only about 20 percent more input, but more than twice the latency, because E11 also emitted more than twice as many output tokens (107 vs 50). A short document is therefore a poor basis for estimating model workload: cost in time tracks generated length at least as much as source length.
