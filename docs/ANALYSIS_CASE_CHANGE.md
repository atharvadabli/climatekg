# Analysis-case indexing change

## Problem

P000100 uses one 2000-2020 moisture-tracking setup, then compares the wettest and driest years at each grid cell. The old representation had only Contexts, Facets, Transitions, and Claims. It therefore forced a bad choice: invent wet/dry study settings, hide the comparison in prose, or omit it. The production run omitted SourceBlock `P000100:S12:P0063` and could not answer the wet/dry query.

The trace also showed two independent implementation causes:

1. Paper mapping was the only gate for starting Context-level Claim extraction when a paper also contained Transitions.
2. A 13,159-token paper was sent through whole-paper mapping. With prompt and schema overhead, the first P000100 response exceeded the 32K context window and was truncated. Its retry compressed settings and omitted the target passage.

## Minimal change

- Keep Context, Facet, Transition, Claim, State, and graph edges unchanged.
- Add optional `Claim.analysis_cases` and `Claim.analysis_comparison` fields.
- Add optional query `analysis_cases` and `analysis_comparison` fields.
- Keep analysis-case matching separate from environmental Context applicability.
- Include analysis-case text in Claim embeddings and persist one embedding per case.
- Start a result-only Claim scan for parent settings of Transition endpoints. Exclude sections already assigned to Transition claim seeds.
- Route cleaned papers above 10,000 tokens through section scouts instead of whole-paper mapping.
- Strip runtime embeddings before LLM calls and synthesis-budget calculations.

Older JSON remains valid because all new scientific fields default to empty or null.

## Validation

Artifacts are under `climatekg/runtime/outputs/analysis_case_validation/`.

- Query parse v5 correctly returns source, target, null intervention, wet/dry analysis cases, and the requested comparison.
- P000100 result-only extraction returns five Context Claims without re-extracting Transition sections.
- Claim `P000100_CL011` compares `Driest years` with `Wettest years` and cites only `P000100:S12:P0063`.
- The one-paper Parquet graph contains 14 Claims and 23 States. Both analysis-case Claims survive Parquet round-trip with 2048-dimensional case embeddings.
- The original wet/dry query ranks `P000100_CL011` first and produces a grounded answer citing that Claim and SourceBlock.
- A backward-compatibility graph rebuild loaded and round-tripped 114 existing papers, 1,706 Claims, 1,195 Contexts, and 3,407 Facets without modifying old Claims.

## Remaining evaluation

The 114-paper compatibility run tests graph construction, not extraction recall on every paper. A later corpus evaluation should annotate a sample of seasonal, percentile, subregion, and wet/dry findings and measure whether the new Claim-level representation improves recall without duplicating Transition Claims.
