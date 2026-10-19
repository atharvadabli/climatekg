# Single-Synthesis Timing Experiment

## Step 1: Remove intermediate synthesis

Compound questions retain independent parsing, Context retrieval, Claim gating, path search, and
evidence selection for every subquery. Subquery runs stop at `evidence_ready`. Their selected Claims
and SourceBlock references are deduplicated and passed to one combined grounded synthesis call.

The first controlled case used the same graph, question, and low-reasoning setting as the earlier
five-query decomposition benchmark. The combined request was 45,160 bytes. The final generation had
not completed 458 seconds after the request was written, and total query time had exceeded ten
minutes. The run was terminated without an answer.

This means fewer LLM calls alone does not solve latency. A larger combined evidence package can cause
Qwen's low-reasoning generation to expand enough to erase the expected saving. The next isolated
change is to disable thinking for the single combined synthesis call while leaving retrieval and
grounding unchanged.
