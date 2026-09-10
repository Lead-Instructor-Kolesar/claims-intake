The shortest case (E12) used 228 input tokens at 5348 ms, while the longest (E11) used 274 input tokens at 4692 ms, about 1.20 times the input size but only 0.88 times the latency.
Input tokens rose with document length, but wall time did not track that increase in this run.
A workload estimate built only from the shortest case would understate token demand on longer documents and could misread latency when the first call pays a cold-start cost.
