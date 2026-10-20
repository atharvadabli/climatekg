# Phase-Batched Query Pipeline: 20-Query Test

## Scope

The phase-batched query pipeline was run on the first 20 cases in
`dataset_v3_current_findings_30/cases.json`. The graph contained 115 papers, 1,221 Contexts, 3,466
Facets, 1,724 Claims, and 2,363 canonical States. Every query used live decomposition and live query
parsing.

Artifacts are stored under:

```text
evaluation/output/query_phase_batching_v1/phase_batched_20/
evaluation/output/query_phase_batching_v1/reference_judge_20/
```

## Completion and latency

All 20 queries completed. One case initially failed because the benchmark worktree redirected the
shared watershed and Koppen files to a nonexistent `worktree/assets` directory. The runner now points
explicitly to the main project's shared assets. `CKGQ0005` then completed with the configured Earth
Engine project.

| Query group | Cases | Mean | Median | P90 |
|---|---:|---:|---:|---:|
| All | 20 | 94.9 s | 71.5 s | 156.5 s |
| One retrieval | 3 | 190.8 s | 214.9 s | 238.6 s |
| Decomposed | 17 | 78.0 s | 69.7 s | 101.5 s |

The completed per-query times sum to 31.6 minutes. The three single-retrieval questions are slower
because they retain the original low/medium-reasoning synthesis. Decomposed questions use one
no-thinking combined synthesis.

## Retrieval and answer quality

- The expected paper appeared among Context or Claim candidates for all 20 questions.
- The final evidence package retained an expected paper for 17 of 20 questions.
- Mean reference-token F1 was 0.300. Mean exact required-term coverage was 0.197. These lexical
  metrics undercount paraphrases and are diagnostic only.
- A single no-thinking Qwen review against the reference answers classified 9 answers as correct, 3
  as mostly correct, 2 as partly correct, and 6 as incorrect. Mean correctness was 2.50/4 and mean
  completeness was 2.45/4.

The Qwen review is not ground truth. Manual inspection confirmed the eight answers marked partly
correct or incorrect and identified the pipeline stage responsible for each.

## Weak cases

| Case | Observed failure | Root stage |
|---|---|---|
| `CKGQ0001` | Answer said wet/dry evidence was absent and substituted evaporative-stress results. | The 115-paper graph contained a stale, nine-Claim extraction of `P000100`. A later validated extraction contains the required finding as `P000100_CL011`, but that paper artifact had not been propagated into this graph. |
| `CKGQ0006` | Correct El Nino direction, but omitted the requested 74% versus 49% frequencies. | Those exact frequency findings are absent from the indexed Claims; selected evidence contains temperature magnitudes instead. |
| `CKGQ0007` | Answer said ENSO-conditioned evidence was absent. | Decomposition and ENSO Facets were correct, but parsing left both requested outcomes inside intervention text and produced no target. Correct `P000040` Claims ranked 29-36 and fell below the eight direct-evidence slots. |
| `CKGQ0011` | Answer rejected the September maximum and substituted a June/August Sahel result. | The expected explanation is not represented by the indexed `P000040` Claims. Cross-paper seasonal evidence then dominated synthesis. |
| `CKGQ0026` | Returned general irrigation cooling and omitted `0.5 K` cooling and `1 K` Canadian warming. | The exact `P000003_CL006` and `P000003_CL007` Claims were candidates, but ranked 23-31 and were removed by the eight-item evidence cutoff. |
| `CKGQ0029` | Returned `4.3 mm year-1` precipitation but omitted `0.767%` humidity and the 25% irrigation fraction. | `P000003_CL005` was selected; `P000003_CL004` ranked 24/31 in the humidity subquery and was not selected. |
| `CKGQ0031` | Mixed some relevant WRF findings with unrelated regions and did not answer the requested common transformation. | The four-way regional decomposition repeatedly selected the same partial `P000021` findings. The indexed Claims do not contain the complete reference finding for all named regions. |
| `CKGQ0033` | Returned no grounded answer although the correct mechanism chain exists. | Parsing produced a forward query with no rainfall target. Exact source-endpoint matching gave an unrelated discharge Claim an endpoint score of 1.0; the correct `P000068_CL001 -> CL002 -> CL003 -> CL006` chain was not assembled into the final evidence. |

## Strong cases

`CKGQ0002`, `CKGQ0003`, `CKGQ0005`, `CKGQ0008`, `CKGQ0010`, `CKGQ0013`, `CKGQ0015`,
`CKGQ0030`, and `CKGQ0032` reproduced the central reference findings. `CKGQ0004`, `CKGQ0009`, and
`CKGQ0028` were scientifically aligned but omitted a secondary explanation or numerical qualifier.

## Conclusion

Phase batching remains useful: compound-query median latency is 69.7 seconds, compared with 551.5
seconds for the original per-subquery synthesis architecture. The larger test does not support a
claim that retrieval quality is solved. Candidate retrieval recall is strong, but query parsing,
missing indexed findings, and fixed evidence truncation still determine whether the correct evidence
reaches synthesis.

The next experiment should preserve evidence separately for each requested outcome or mechanism step
before applying a global evidence limit. It should not increase the limit indiscriminately: the
failure is loss of query-role coverage, not an insufficient total number of candidates.

## P000100 artifact-lineage correction

The `CKGQ0001` diagnosis was checked against the paper artifacts. The result was present in cleaned
text and SourceBlock `P000100:S12:P0063`. The earlier corpus extraction had nine Claims and omitted
the result, while the later analysis-case extraction had 14 Claims and represented it as
`P000100_CL011`, including separate wettest- and driest-year analysis cases.

A corrected 115-paper graph was built by replacing only `P000100` with that validated artifact. The
graph round-trip retained `P000100_CL011` and its SourceBlock provenance. Rerunning `CKGQ0001` with
the same live query pipeline returned the requested direction and magnitude:

> The contribution is higher during dry years than wet years and exceeds 20% in the
> Indo-Gangetic Plain during the driest years.

The answer cited `P000100_CL011`; that Claim ranked first and formed the first direct evidence path.
This establishes that the original failure was stale graph lineage rather than query retrieval or
synthesis for this case.

Artifacts:

```text
climatekg/runtime/outputs/three_system_benchmark/parquet_graph_analysis_case_patch_v1/
evaluation/output/query_phase_batching_v1/p000100_patch_ckgq0001/
```
