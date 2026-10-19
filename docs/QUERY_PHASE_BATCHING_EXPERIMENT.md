# Query Phase-Batching Experiment

## Change

Compound queries previously executed each subquery from parsing through retrieval before starting the
next subquery. That repeatedly exchanged the generation and embedding models. This experiment changes
only execution order:

```text
decompose
-> parse every fresh subquery
-> embed, retrieve, gate, and search each subquery
-> one combined grounded synthesis
```

The prompts, reasoning levels, `QuerySpec`, graph algorithms, thresholds, evidence quotas, and final
synthesis package are unchanged. Cached retrieval-only subquery reports remain reusable.

## Timing

| Case | Single synthesis | Phase batched | Ratio |
|---|---:|---:|---:|
| CKGQ0001 | 132.9 s | 187.5 s | 0.71x |
| CKGQ0003 | 118.9 s | 90.7 s | 1.31x |
| CKGQ0009 | 110.4 s | 81.7 s | 1.35x |
| CKGQ0029 | 78.1 s | 65.7 s | 1.19x |
| CKGQ0032 | 93.2 s | 70.9 s | 1.31x |

Median latency fell from 110.4 to 81.7 seconds. The first cold-start case was slower, while the four
following cases improved by 19--35%. Across the five cases, query-parse LLM time fell from 190.2 to
103.7 seconds. Combined-synthesis time remained similar, as expected.

## Quality

All five expected papers were still retrieved. Reference-token overlap improved or remained unchanged
for every case. A blinded LLM review scored correctness at 3.2/4 for both versions and directness at
1.6/2 for both. It scored completeness at 3.2 for the previous version and 2.8 for phase batching.

Manual inspection found one real omitted detail: CKGQ0003 retained the supported higher-altitude
circulation result but omitted the specific 840 hPa value. The judge also penalized CKGQ0009 for
omitting a local nighttime increase above 2 K, although neither compared answer contained that detail.
That penalty is judge instability rather than a phase-batching regression.

The phase-batched CKGQ0009 answer used only the three directly relevant P000004 Claims instead of
adding less direct P000039 Claims, while preserving daytime cooling, nighttime warming, and reduced
heat-wave duration. CKGQ0032 retained the exact P000082_CL004 to P000082_CL005 connection.

## Decision

Keep phase batching. It changes scheduling rather than scientific behavior, reduces steady-state
latency, preserves expected-paper retrieval and correctness, and produces more focused provenance in
some cases. Cold-start model loading remains a separate deployment issue.

## Artifacts

```text
evaluation/output/query_phase_batching_v1/phase_batched_5/
evaluation/output/query_phase_batching_v1/blinded_judge_5/
```
