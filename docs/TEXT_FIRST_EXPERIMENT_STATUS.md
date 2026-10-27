# Text-first Claim extraction: paused experiment

Date: 2026-10-27. Code branch: `experiment/text-first-claim-extraction-v1`.
Runtime artifacts: `climatekg/runtime/outputs/text_first_claims_v1` and
`climatekg/runtime/outputs/text_first_claims_v2` in the original workspace.

The current Claim pass selects evidence around mapped settings. The experiment
instead showed Qwen every cleaned non-reference passage in section-aware windows,
with the existing setting hierarchy and Facets supplied for scope assignment.
It replaced the Claim pass; old Claims were neither input nor additive output.

## Observed

| Paper | Status | Observation |
|---|---|---|
| P000100 | complete Claim-stage replay | 9 old Claims versus 16 new; wet/dry rainfall comparison, >20% IGP, seasonal contrast, March blue-water peak, and stress-season findings were extracted. Existing Contexts, Facets and Transitions stayed unchanged. |
| P000018 | interrupted after several windows | A first pass fabricated one passage ID and was rejected. A later pass constrained IDs to the supplied window. It also attached a homogeneous zero-wind Facet to a heterogeneous finding; the invalid link was removed and logged under the specified rule. Full-paper result is incomplete. |
| P000068 | not reached | No conclusion. |

P000100 extraction took 243 seconds on the second pass, plus about 7 seconds
for State canonicalization and embedding. The first pass took 171 seconds.
Per-call prompts, raw responses, and timings are in each window directory.
The second pass used 3,000-token windows and a JSON schema that restricted
evidence IDs to passage IDs actually supplied in that window.

The P000100 upper-bound caveat was still omitted even though it appeared in the
same passage as a recovered stress-phase finding. It is an extraction omission,
not a passage-selection failure. Some P000018 wind and patch statements also
need source-level review for scope and tested-value precision. More Claims does
not establish better scientific coverage.

This is a partial fixed-registry Claim replay, not PDF-to-graph validation or a
manually judged benchmark. No 10-paper or 30-paper expansion was run. The text-
window mode is **not included** in this integration branch. Continue its review
on the experiment branch, then test unchanged previously good findings before
considering adoption.
