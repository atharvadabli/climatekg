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

## Step 2: Disable thinking for combined synthesis

The same five compound questions were rerun with `query_combined_synthesis.thinking=no`. No retrieval
threshold, evidence quota, graph operation, prompt task, or grounding check changed. A dependent-join
regression was corrected deterministically: the upstream paper handoff now uses the direct Claim with
the highest semantic match rather than the first overall-ranked path.

| Case | Previous decomposition | Single synthesis, no thinking | Speed-up |
|---|---:|---:|---:|
| CKGQ0001 | 551.5 s | 132.9 s | 4.15x |
| CKGQ0003 | 632.6 s | 118.9 s | 5.32x |
| CKGQ0009 | 588.0 s | 110.4 s | 5.33x |
| CKGQ0029 | 499.4 s | 78.1 s | 6.40x |
| CKGQ0032 | 322.1 s | 93.2 s | 3.46x |

Median latency fell from 551.5 to 110.4 seconds. The combined synthesis calls averaged 38.2 seconds
and generated 1,551 tokens across five calls. Query parsing now consumes about as much total LLM time
as final synthesis because the generation and embedding models are repeatedly exchanged between
subqueries.

A blinded comparison against the previous decomposed answers found:

| System | Correctness /4 | Completeness /4 | Directness /2 |
|---|---:|---:|---:|
| Previous decomposed pipeline | 3.6 | 3.8 | 1.4 |
| Single synthesis, no thinking | 3.2 | 3.0 | 1.6 |

The faster answers preserved the main findings for CKGQ0003, CKGQ0009 and CKGQ0032. CKGQ0009 omitted
one secondary nighttime magnitude, and CKGQ0029 omitted some quantitative and seasonal detail. The
CKGQ0001 failure remains an indexing-content problem: the required dry-year finding is absent from the
graph used by this benchmark.

The next latency target is phase-batched query parsing and retrieval, not further weakening final
synthesis. That change should reduce repeated model swaps while retaining the present evidence and
answer behavior.

## Artifacts

```text
evaluation/output/query_single_synthesis_v1/single_synthesis_no_clean2_5/
evaluation/output/query_single_synthesis_v1/single_synthesis_no_joinfix/
evaluation/output/query_single_synthesis_v1/candidate_fixed_5/
evaluation/output/query_single_synthesis_v1/blinded_judge_5/
```
