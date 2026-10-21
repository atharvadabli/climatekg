# P000100 patch: 20-query rerun

## Purpose

The previous 115-paper graph contained a stale nine-Claim extraction of `P000100`. A validated
analysis-case extraction contains 14 Claims, including `P000100_CL011`, which represents the wet-
versus-dry-year rainfall contribution requested by `CKGQ0001`.

This rerun changes only that paper artifact. Query decomposition, parsing, retrieval, evidence
assembly, and synthesis use the same phase-batched implementation as the previous 20-query run.
All questions use live decomposition and live per-subquery parsing.

## Artifacts

```text
climatekg/runtime/outputs/three_system_benchmark/parquet_graph_analysis_case_patch_v1/
evaluation/output/query_phase_batching_v1/p000100_patch_20_rerun/
evaluation/output/query_phase_batching_v1/p000100_patch_judge_batches/
```

The corrected graph contains 115 papers and 1,729 Claims. `P000100_CL011` and its provenance to
SourceBlock `P000100:S12:P0063` were verified after reading the Parquet graph back.

## Aggregate results

| Metric | Previous run | Patched rerun |
|---|---:|---:|
| Completed queries | 20/20 | 20/20 |
| Expected-paper hits | 17/20 | 17/20 |
| Mean reference-token F1 | 0.3004 | 0.3217 |
| Median reference-token F1 | 0.2828 | 0.3316 |
| Mean exact qualifier coverage | 0.1967 | 0.2258 |
| Median latency | 71.5 s | 76.0 s |
| Mean latency | 94.9 s | 111.0 s |
| Paired-review correctness | 2.9/4 | 3.1/4 |
| Paired-review completeness | 2.5/4 | 2.6/4 |
| Paired-review directness | 1.45/2 | 1.55/2 |

The latency difference is run-to-run measurement, not evidence that replacing one paper caused a
systematic slowdown. Both runs use live local-LLM calls and were executed once.

## Paired reference review

The same local Qwen model blindly scored the previous and patched answers against each reference
answer. This review is diagnostic rather than ground truth.

| Correctness band | Previous run | Patched rerun |
|---|---:|---:|
| Correct (4/4) | 11 | 13 |
| Mostly correct (3/4) | 3 | 2 |
| Partly correct (2/4) | 1 | 1 |
| Incorrect (0-1/4) | 5 | 4 |

No case lost scientific-correctness points in this paired review. Two cases improved:

- `CKGQ0001`: `1/4` to `4/4`. The corrected Claim ranked first, and the answer stated that the
  contribution is higher in dry years and exceeds 20% in the Indo-Gangetic Plain.
- `CKGQ0028`: `3/4` to `4/4`. The rerun answered the cooling and diurnal-temperature-range effects
  more directly, although this change is generation variability rather than a direct consequence of
  the P000100 replacement.

## Remaining incorrect cases

- `CKGQ0007`: still returns insufficient evidence for the requested El Nino-versus-La Nina outcome
  comparison.
- `CKGQ0011`: still rejects the requested September maximum and misses the preceding-rainfall and
  soil-moisture explanation.
- `CKGQ0026`: still omits the requested regional temperature magnitudes, including northern Canada.
- `CKGQ0033`: still returns no scientific answer because the required mechanism chain does not reach
  final evidence.

The P000100 correction therefore fixes the failure it was intended to fix without solving unrelated
query-parsing, evidence-coverage, or path-construction failures.
