# Text-first Claim extraction experiment

Branch: `experiment/text-first-claim-extraction-v1`.

## Question

Can a first-pass extraction driven by paper text recover findings missed by
scope-selected evidence, while retaining the existing study-setting hierarchy?

## Design

Keep mapping and Facet extraction unchanged. Replace, rather than supplement,
the staged Claim pass with section-aware, token-bounded windows of cleaned text.
Each window receives the full setting/comparison registry and reported conditions.
Qwen extracts relationships and assigns their scope in the same call. Old Claims
are not provided to the model and are not retained in the experimental result.

This initial conservative implementation includes all non-reference content;
title/heading blocks are omitted but each passage retains its section path.
This avoids relying on Results heading recognition or a second LLM selector.
Background attribution remains explicit and only own findings/interpretations
enter the graph. Captions, tables, and unusually named sections remain eligible.

Use `evidence_retrieval.claim_extraction_mode = "text_windows"` in constants.py
to enable the experimental route for staged indexing. The default remains
`scope_retrieval`; combined small-paper extraction is unchanged.

## Pilot

- [x] Confirm old evidence-selection failure in implementation.
- [x] Add isolated mode, standalone prompt, reference checks, cache fingerprints.
- [x] Run P000100; P000018 stopped after several windows; P000068 was not reached.
- [ ] Complete source-level review, including old findings that were lost.
- [ ] Decide whether to proceed to ten papers. Thirty remains gated.

`scripts/run_text_first_claims.py` replays only Claim extraction with fixed
Contexts/Facets/Transitions from a baseline graph, then canonicalizes and embeds
Claims and writes a separate Parquet graph. This isolates extraction behavior;
it is not a new PDF-to-graph run. Pilot consolidation is exact-only. The normal
indexer retains its existing reconciliation and semantic consolidation stages.

## Evidence to inspect

Every window saves the actual request, response (including thinking when enabled),
schema, timings, validated output and cache fingerprint. `coverage.json` records
all eligible/excluded passages and successful windows. Input coverage is NOT
Claim recall. `claims.json` stores pre-embedding extraction. `benchmark.json`
records runtime, Claim counts and unchanged registry checks.

Evaluate correct ownership, direct provenance, background exclusion, preservation
of mechanisms and qualifiers, duplicate findings, unresolved scopes and time.
More Claims alone is not success. A full registry may exceed the context budget;
the experiment then fails explicitly rather than truncating it. Window boundaries
can lose distant references; inspect this before adding overlap or retrieval.

## Reproduce the pilot

From this experimental worktree, using the existing project Python environment:

```powershell
python scripts/run_text_first_claims.py --source-graph <baseline_10_graph> --output <new_output_directory> --papers P000100 P000018 P000068
```

Use distinct output directories for experiments. The root workspace holds the
actual `text_first_claims_v1` and `text_first_claims_v2` outputs below
`climatekg/runtime/outputs`. Review
`evaluation/text_first_claims/benchmark.md` for failures and measured findings.
Version 2 uses 3,000-token windows and constrains evidence IDs during generation.
The pilot was paused before all three papers finished. Do not treat the saved
partial outputs as a completed indexing run or merge this route into deployment.
