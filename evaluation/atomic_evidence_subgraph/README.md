# Atomic Evidence-Subgraph Experiment

This experiment tests whether ClimateKG can recover scientifically supported
mechanism structures without requiring every useful Claim to participate in an
exact lexical State-to-State path.

The experiment is intentionally gated. It starts with ten papers. Expansion to
thirty papers is allowed only after the ten-paper results satisfy the criteria
below. Criteria are fixed before implementation or model execution.

## Ten-paper corpus

The corpus is defined in `corpus_10.json`. It covers:

- deforestation, clouds, and radiative feedback;
- forest-related cloud enhancement;
- wet-dry surface heterogeneity and convection;
- irrigation cooling and moist-heat trade-offs;
- Indian monsoon circulation and precipitation;
- land-cover change over India;
- local and remote moisture recycling;
- cross-basin hydrological teleconnections.

## Changes under test

1. Claim extraction makes each directly supported mechanism step a separate
   Claim. It does not add scientifically plausible but unstated intermediates.
2. Detailed endpoint wording is retained. Verified semantic links may describe
   endpoint identity or hierarchy without becoming causal evidence.
3. Query retrieval selects a compact, Context-compatible evidence subgraph that
   covers the question. A useful Claim is not discarded solely because no exact
   multi-edge State path reaches it.

## Required artifacts

Every run must preserve:

- the exact paper manifest and code revision;
- every LLM request, response, thinking output, validation result, and timing;
- extracted Claims and SourceBlock provenance;
- proposed, accepted, and rejected State semantic links;
- query parsing, candidates, Context scores, selected paths, selected evidence
  subgraph, uncovered requirements, synthesis package, and final answer;
- a paper-by-paper and query-by-query comparison with the existing baseline.

## Ten-paper gate

The experiment passes only if all of the following hold:

1. All finalized Claims and semantic links pass schema and provenance checks.
2. No reviewed semantic link merges a mechanism with its outcome, opposite
   directions, distinct physical variables, or different spatial relation
   families.
3. No causal connection is created from embedding similarity or hierarchy
   alone.
4. At least 90% of manually expected atomic mechanism steps are extracted from
   the ten papers, measured against the frozen diagnostic annotations.
5. At least 75% of expected Claims or their verified atomic replacements reach
   the selected evidence subgraph for the diagnostic queries.
6. Evidence-subgraph coverage exceeds the existing selected-path coverage on
   the same questions without reducing candidate retrieval coverage.
7. Every substantive answer statement is supported by selected Claim and
   SourceBlock provenance.
8. At least 80% of answers are judged `correct` or `mostly_correct`; none may be
   judged incorrect because an unsupported graph bridge was introduced.
9. Existing Context incompatibility and spatial-transfer safeguards continue to
   pass their deterministic tests.

If the gate fails, record the earliest failing stage, revise only the responsible
stage, and rerun the same frozen ten-paper suite. Do not expand the corpus until
the gate passes.

## Thirty-paper expansion

After the gate passes, freeze the implementation and add twenty papers selected
for additional climates, study types, mechanisms, null findings, contradictions,
and spatial scales. Do not tune prompts or thresholds on the thirty-paper result.

