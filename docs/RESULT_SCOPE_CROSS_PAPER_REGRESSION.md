# Focused Result-Scope Cross-Paper Regression

## Purpose

This regression tests the focused result-scope indexing design on papers with different scientific structures. It compares newly generated artifacts with the existing `indexing_50_medium_map_20260829` baseline. Parsing, cleaning, and SourceBlocks were reused; mapping and every downstream stage were rebuilt with `qwen3.6:27b`.

The complete run, including failed attempts and targeted reruns, took about 179.4 minutes (2.99 hours). Exact prompts, responses, thinking output, timings, and final artifacts are stored under:

```text
climatekg/runtime/outputs/result_scope_cross_paper_v1/
```

## Papers

| Paper | Scientific stress case |
|---|---|
| P000006 | Observed versus modeled soil-moisture and afternoon-rainfall feedback |
| P000019 | Season, background wind, deforestation, resolution, clouds, and rainfall |
| P000056 | CTRL/DRY configurations, seasons, sites, and observational products |
| P000068 | Historical versus present land cover and Indian monsoon responses |
| P000100 | Upwind irrigation recycling, wet/dry years, seasons, and Indian subregions |

## Final indexing results

| Paper | Status | Final run (min) | LLM calls | Old C/F/T/Cl | New C/F/T/Cl | Claims with cases |
|---|---:|---:|---:|---:|---:|---:|
| P000006 | complete | 16.64 | 10 | 3/15/1/3 | 3/14/1/18 | 4 |
| P000019 | complete | 29.66 | 29 | 20/44/8/33 | 20/30/5/43 | 13 |
| P000056 | complete | 29.16 | 20 | 16/47/5/25 | 3/9/1/74 | 47 |
| P000068 | `NEEDS_REVIEW` | 20.77 | 4 | 7/24/3/25 | not produced | not produced |
| P000100 | complete | 22.61 | 19 | 8/20/3/9 | 5/16/2/39 | 19 |

`C/F/T/Cl` means Contexts, Facets, Transitions, and Claims. LLM time accounts for almost all successful indexing time: 15.97, 29.03, 26.18, and 21.98 minutes for P000006, P000019, P000056, and P000100 respectively.

## What improved

Focused result scopes materially increased Claim coverage in all four completed papers. The strongest verified case is P000100. Its baseline contained 9 Claims and no structured analysis cases; the new artifact contains 39 Claims, 19 Claims with cases, and 7 explicit case comparisons.

The previously missing wet/dry finding is now represented directly:

```text
P000100_CL002
The contribution of upwind irrigated crop evaporation to rainfall over
rainfed regions is consistently higher during the driest years compared
to wetter years, particularly in the Indo-Gangetic Plain where values
exceed 20%.

Cases: Driest years; Wettest years
```

P000006 also improved from 3 to 18 Claims while retaining its three-setting observational/model hierarchy. P000019 retained all 20 Contexts and increased from 33 to 43 Claims.

## Failures found and fixes tested

### Missing Context evidence was sent to the wrong repair

The first P000019 attempt failed because three mapped Contexts had empty `evidence_block_ids`. The existing generic handler sent this error to a repair path for comparisons with identical endpoints. Qwen filled the missing evidence, but `_apply_map_repair()` correctly discarded those changes because it only permits comparison-endpoint additions.

The implementation now detects missing Context evidence separately. Its repair request receives the exact missing Context IDs and selected original passages. The applier permits changes only to `evidence_block_ids` on originally empty Contexts. P000019 then completed.

### Invalid analysis comparison was detected too late

The first P000056 attempt reached final assembly before failing. `P000056_CL003` declared only the case `DJF season`, while its comparison named `CTRL simulation configuration` and `DRY simulation configuration`. Those labels were not cases on that Claim.

The same invariant is now enforced by `ClaimCandidate` and `Claim`. Invalid output is rejected while decoding the Claim response, allowing the existing bounded structured-output retry to correct it before downstream work. P000056 then completed.

### Result-scope coverage still fails for P000068

The first P000068 attempt omitted `P000068:S18:P0088`. The map-consolidation prompt now receives a concise checklist of every required result SourceBlock ID. The rerun nevertheless omitted `P000068:S15:P0069` and `P000068:S18:P0088`.

`P000068:S15:P0069` was included in the selected original passages. `P000068:S18:P0088` was listed in scout notes and the required-ID checklist but was dropped from the selected original passages because the 9,000-token source budget was full. This is not solved by stronger prompt wording alone. The current visible failure is preferable to silently losing the findings, but a bounded coverage-repair design or a revised map-input packing rule is still required.

## Structural regressions

Higher Claim counts do not establish a better graph.

- P000019 retained 20 Contexts but dropped from 8 to 5 Transitions. The new map omitted explicit original-versus-reduced-wind and 2-km-versus-4-km comparisons even though their endpoint settings remain present.
- P000056 collapsed from 16 Contexts to 3. Treating SON/DJF summaries as analysis cases is correct, but flux-tower sites, forcing datasets, and observational products were also removed as separately matchable settings. That loss needs scientific review.
- P000100 correctly moved wet/dry years and subregions into analysis cases, but it also collapsed distinct rainfed-target and irrigated self-recycling branches. The resulting Claims are richer, while graph-level population matching may be weaker.

These changes mean the focused result-scope branch should not yet be merged on Claim recall alone.

## Query regression

A Parquet graph was built from the four successful papers:

```text
4 papers
602 SourceBlocks
31 Contexts
69 Facets
9 Transitions
174 Claims
277 canonical States
1,884 relationships
```

Two queries were run with full trace artifacts under `queries/RSQ001` and `queries/RSQ002`.

1. The irrigation wet/dry query passed. The answer states that the upwind irrigated-crop contribution is higher in dry years, exceeds 20% in the Indo-Gangetic Plain, and is lower during the wetter monsoon season. It cites P000100 Claims.
2. The Rondonia heterogeneity query was partly correct. It recovered the rainy-season null effect and dry-season enhancement, but omitted the break-period reduced-wind result and described dry-season winds too loosely as weak. This remains a retrieval/synthesis regression to trace.

## Decision

The result-scope design improves under-extracted findings and resolves the priority P000100 wet/dry query. It is not yet ready to merge because:

- P000068 cannot complete map coverage;
- important comparison edges disappeared in P000019;
- P000056 and P000100 lost potentially useful setting branches; and
- the heterogeneity query did not synthesize all retrieved seasonal/wind regimes accurately.

The next change should address result-block coverage and setting/Transition preservation together. Adding another general-purpose LLM polishing call would hide these structural errors and is not recommended.
