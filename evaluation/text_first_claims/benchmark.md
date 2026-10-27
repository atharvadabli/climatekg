# Text-first Claim extraction pilot

Date: 2026-10-27. Branch: `experiment/text-first-claim-extraction-v1`.

## Controlled comparison

Use the baseline 10-paper graph's SourceBlocks, Contexts, Facets and Transitions.
Re-extract Claims from text windows, without old Claims as input or additive output.
Generate new State embeddings and a separate Parquet graph. This is a Claim-stage
replay, not a fresh PDF parsing or mapping benchmark. No query or answer-score
improvement has been measured in this experiment.

Pilot papers: P000100 (irrigation recycling), P000018 (heterogeneity and wind),
P000068 (forest conversion). Review source evidence, not just Claim counts.

## First attempt: 6,000-token text windows

- P000100: 4 calls, 170.9 s extraction, 6.4 s canonicalization/embedding,
  9 baseline Claims -> 10 newly extracted Claims; all 8 Contexts, 20 Facets,
  and 3 Transitions unchanged.
- Recovered rainfall contribution in driest years and >20% in the IGP, the
  seasonal rainfall contrast, and March's maximum blue-water contribution.
- Still missed old stress-season findings and the upper-limit caveat.
- The dry-year record retained only the driest case and a null comparison.
  It also overstated potential moisture buffering as an established result.
- The abstract window wrongly abstained because its evidence IDs were not in
  the setting registry's provenance lists. Those lists are unnecessary input.
- P000018 stopped at window 1: generated `P000018:S00:P0006` rather than actual
  `P000018:S01:P0006`. The cited scientific text was present, but the copied ID
  was wrong. The invalid response was saved and rejected, not silently repaired.
- That response ended normally (`done_reason=stop`), with 16,946 prompt tokens
  and 4,136 output tokens, below the 32,768-token context. Thinking was disabled
  by the existing validated Claim-extraction profile; there is no thinking trace.
- P000068 was not reached in this attempt.

Artifacts: `climatekg/runtime/outputs/text_first_claims_v1` in the root workspace.

## Second attempt

General changes, not paper-specific examples:

1. Constrain evidence ID fields to actual window IDs in the JSON schema.
2. Remove setting-provenance IDs from the registry; keep setting identity,
   hierarchy, aliases, spatial support, comparisons and condition descriptions.
3. Use 3,000-token text windows, keeping the same model and reasoning profile.
4. Clarify preservation of both comparison cases, explanations and limitations.

These changes are tested together; this pilot cannot attribute improvements to
one change independently. Exact reference validation remains; scientific wording
is open and is not compared by exact string matching.

Artifacts: `climatekg/runtime/outputs/text_first_claims_v2` in the root workspace.

Observed second-pass status: P000100 completed in 242.8 s of Claim extraction
and 7.1 s of canonicalization/embedding, yielding 16 new Claims from 9 old
Claims. The wet/dry comparison is now explicit with both year groups and an
exact Results 3.1 citation. Non-monsoon and pre-monsoon stress findings were
also recovered. The upper-bound caveat was still omitted despite being in the
same `P000100:S13:P0078` passage as a recovered stress-phase finding.

P000018's first window and several subsequent windows ran, but the run was
interrupted before final paper materialization. The second window included an
incorrect conditioning link to `P000018_F012`, a zero-wind Facet belonging to
a homogeneous experiment, on a heterogeneous-Context Claim. This link was
removed according to the specification and the output remains available for
review. Some wind statements also need source-level checks for tested-value
precision. P000068 did not run. No 10- or 30-paper expansion followed.

## Review checklist

- P000100: wet/dry comparison; total versus blue-only water; seasonal rainfall
  and stress; upper-bound assumption; self-recycling/water demand.
- P000018: surface contrast -> circulation -> moisture transport/pooling ->
  convection; tested patch sizes and wind comparisons; correct scope ownership;
  no universal threshold invented from tested values.
- P000068: roughness/wind; evapotranspiration; instability; radiation; sensible
  heat; rainfall effects and their conditions.
- All papers: distinguish own results, interpretations and cited literature;
  inspect missing old findings, duplicates, and unsupported clause-level additions.

Passage coverage does not establish finding recall. Agent review is preliminary,
not an independent gold-standard evaluation. Thirty-paper expansion remains gated.
