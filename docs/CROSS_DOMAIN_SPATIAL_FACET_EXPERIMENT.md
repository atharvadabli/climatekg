# Cross-domain spatial Facet experiment

## Purpose

The failed `CKGQ0001` trace showed that the query represented an upwind
source-to-receptor relation as `spatial_configuration`, while `P000100` stored
the same evidence only as `land_surface`, `hydrology`, and Claim text. This
experiment tests an additive rule: one evidence statement may support separate
Facets in several domains, with shared evidence provenance.

## Implementation

- `Facet.domain` remains single-valued; the schema is unchanged.
- The staged and combined prompts create separate domain-focused Facets when one
  condition has several independently useful aspects.
- Explicit source/sink, upwind/downwind, patch, edge, distance, orientation, and
  similar physical relations receive a `spatial_configuration` Facet while the
  associated land-surface, water, atmosphere, climate, and terrain Facets remain.
- A target Context's `evidence_block_ids` and `facet_seed_block_ids` are both
  mandatory in Facet evidence retrieval.
- Parent Facet retrieval no longer searches child Context aliases.
- Root Context Facet extraction uses low reasoning. Descendants use no reasoning.
- Explicit response relationships accidentally returned as Facets are excluded
  deterministically and recorded in `excluded_outcomes.json`; they remain
  available to Claim extraction.

## Prompt development

All candidates used fixed paper maps. Strict prompt comparisons reused identical
SourceBlock bundles; final tests rebuilt bundles with the new ownership rules.

| Candidate | Finding |
|---|---|
| Long domain guide | Added the missing spatial relation but changed unrelated domain assignments and omitted a useful climate condition. Rejected. |
| Short additive rule | Reduced classification drift, but no-reasoning root calls still mixed parent and child conditions. |
| Stronger spatial boundary | Prevented several false spatial records, but could not solve Context ownership while child evidence remained prominent. |
| Target-owned bundles | Removed child-alias expansion and made mapped Context evidence mandatory. Parent/child ownership improved. |
| Root-only low reasoning | Produced coherent root Facets while keeping descendant calls fast. Accepted. |

The three-paper regression corpus was:

- `P000100`: irrigation moisture source/sink geometry and wet/dry analysis cases;
- `P000040`: river-basin irrigation experiments, reanalysis, coupled simulations,
  and spin-up sensitivity settings;
- `P000056`: seasonal soil-moisture regimes, model configurations, and
  observational validation sites.

The accepted `P000100` replay retained nine setting Facets. Its new spatial
Facet is:

```text
notion: Target and source region delineation
description: The target region comprises Indian grid cells containing rainfed
and irrigated crops. The source region encompasses irrigated land whose moisture
contribution is evaluated for rainfed crops cultivated downwind.
```

One outcome-like candidate, "Reduced rainfall over rainfed regions", was saved
to `extraction/facets/excluded_outcomes.json` and excluded from applicability
Facets. Claim extraction retained the relationship as scientific evidence.

## Downstream result

The fixed-map `P000100` downstream replay produced:

| Object | Count |
|---|---:|
| Contexts | 4 |
| Facets | 9 |
| Transitions | 2 |
| Claims | 12 |
| States | 20 |

The wet/dry finding remained as `P000100_CL008`, including the two analysis
cases, the Indo-Gangetic Plain qualifier, the value above 20%, and exact evidence
block `P000100:S12:P0063`.

For the unchanged benchmark question, the rebuilt seven-paper graph produced:

| Trace value | Before | After |
|---|---:|---:|
| Retained `P000100` Contexts | 0 | 4 |
| Rank of wet/dry Claim | 1 | 1 |
| Claim applicability `A_claim` | unknown | 0.5278 |
| Claim analysis-case score | 0.7866 | 0.8034 |
| Correct Claim in direct evidence paths | no | yes |
| Grounded answer | incorrect | correct |

The new answer states that the contribution is higher in the driest years than
the wettest years and exceeds 20% in the Indo-Gangetic Plain during dry years,
citing `P000100_CL008`.

## Artifacts

- accepted Facet replay: `climatekg/runtime/outputs/cross_domain_facet_v7_full_p100/P000100`
- rebuilt graph: `climatekg/runtime/outputs/cross_domain_query_v7/parquet_graph`
- query trace: `climatekg/runtime/outputs/cross_domain_query_v7/query/CKGQ0001_cross_domain_v7/query_report.json`
- prompt replay utility: `scripts/run_cross_domain_facet_experiment.py`
- downstream replay utility: `scripts/replay_facets_downstream.py`

The graph still contains inherited Context repetition: all four `P000100`
Contexts inherit the root spatial Facet and receive the same score. That no
longer blocks this paper, but Context-family diversification remains a separate
retrieval experiment for larger corpora.
