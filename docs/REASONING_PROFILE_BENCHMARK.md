# Reasoning Profile Benchmark

## Goal

Measure which Qwen reasoning stages are worth their runtime cost without changing prompts,
schemas, extraction algorithms, or graph construction. The factorial screen varies three factors:

- paper mapping: `low` or `no`;
- Claim extraction: `low` or `no`;
- reconciliation and consolidation: `low` or `no`.

Section scouting and Facet extraction use `no` in every profile. The screening corpus is the
complex irrigation paper `P000003`. Stable parsing artifacts are reused, and exact upstream
outputs are copied when isolating a downstream factor. Estimated fresh times reconstruct the
unchanged and regenerated phase measurements; cache-assisted wall time is never reported as a
fresh indexing time.

## Eight-Profile Screen

| Profile | Estimated fresh min | C/F/T/CL | Duplicate transition endpoints | Gate |
|---|---:|---:|---:|---|
| `map-no_claim-no_down-no` | 22.18 | 11/30/6/31 | 1 | FAIL |
| `map-no_claim-no_down-low` | 24.23 | 11/30/6/31 | 1 | FAIL |
| `map-low_claim-no_down-no` | 25.16 | 11/29/5/22 | 0 | PASS |
| `map-low_claim-no_down-low` | 25.41 | 11/29/5/22 | 0 | PASS |
| `map-low_claim-low_down-no` | 39.94 | 11/29/5/22 | 0 | PASS |
| `map-low_claim-low_down-low` | 40.51 | 11/29/5/22 | 0 | PASS |
| `map-no_claim-low_down-no` | 40.93 | 11/30/6/29 | 1 | FAIL |
| `map-no_claim-low_down-low` | 41.55 | 11/30/6/29 | 1 | FAIL |

`C/F/T/CL` means Contexts, Facets, Transitions, and Claims. Every `map=no` result created a sixth
irrigation comparison whose endpoints duplicated an existing control-versus-irrigated comparison.
Changing Claim or downstream reasoning did not remove that map error. With the same low-reasoning
map held fixed, Claim extraction produced 22 Claims at both `low` and `no`; Claim embeddings had a
median aligned similarity of 0.918. Low Claim reasoning added roughly 15 minutes.

Each local profile directory under
`climatekg/runtime/outputs/reasoning_matrix_p3_20260828` contains `BENCHMARK.md` and
`benchmark.json`. The matrix root contains the combined versions.

## Fresh Cross-Checks

The fastest passing factorial profile, `map-low_claim-no_down-no`, was regenerated normally on two
other papers.

| Paper | Runtime min | C/F/T/CL | Observation |
|---|---:|---:|---|
| `P000001` | 13.47 | 10/28/2/11 | Major wind-farm branches remained, but sensitivity detail was reduced. |
| `P000006` | 11.24 | 6/18/2/6 | Wet/high-soil-moisture regime and its dry-versus-wet comparison were omitted. |

The second omission is scientifically important, so low mapping was not accepted for the large
corpus merely because it was fast. A targeted `map-medium_claim-no_down-no` profile was then run
fresh on three papers.

| Paper | Runtime min | C/F/T/CL | Preserved structure |
|---|---:|---:|---|
| `P000001` | 19.03 | 15/36/8/13 | Field campaign, RAMS control, and seven distinct TKE sensitivity cases. |
| `P000003` | 24.28 | 11/28/5/18 | Five non-duplicated irrigation, soil-column, timing, and coupling comparisons. |
| `P000006` | 13.33 | 7/23/3/7 | Dry/wet regimes and daytime/nighttime precipitation-onset regimes. |

Mean runtime was 18.88 minutes, median runtime was 19.03 minutes, total measured LLM time was
45.58 minutes, and Parquet/FAISS construction took 0.96 seconds. At the measured mean, 50 papers
require about 15.73 serial hours. Generation variance is substantial, so this is a projection, not
a deadline guarantee.

## Selection

Use `map-medium_claim-no_down-no` for the 50-paper benchmark. It is the smallest tested increase
that recovered all required structures in the three-paper cross-check. This selection does not
claim that medium reasoning guarantees complete extraction. It records that `no` caused duplicate
map structure and that a fresh `low` run omitted a material experimental regime.

The 50-paper corpus is fixed in `config/indexing_benchmark_corpus_50.json`. It preserves the
original ten papers and adds a deterministic, relevance-ranked sample across 14 topic folders.
The run is resumable and records exact prompts, responses, phase timings, and Parquet output under
one dedicated runtime directory.
