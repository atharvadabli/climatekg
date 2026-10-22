# Atomic query plan experiment

Branch: `experiment/atomic-query-plan-v1`

## Problem

The previous query path called one LLM to decompose a compound question and then called another LLM
to parse every generated subquery. This increased latency and allowed the second call to change or
drop the source, target, cases, and Context conditions selected by the first call. Fixed top-ranked
evidence slots and Context shortlists could also remove a relevant Claim even when another retrieval
channel found it.

## Changes

- One schema-validated Qwen call now returns an atomic query plan and the structured fields for every
  search. The generated searches are compiled directly to `QuerySpec` objects.
- Separately named cases and outcomes become independent searches. Vague collective contrasts such as
  `other months` are removed when a focal named-case search already preserves the comparison.
- Environmental analysis cases can also be Context Facets when they affect applicability.
- Spatial references are represented as spatial-configuration Facets as well as spatial support.
- Method descriptions emitted as Context Facets and process names emitted as locations are discarded
  deterministically.
- Ellipsis-form query spans are reduced to exact continuous text already present in the question;
  spatial references prefer the final exact location segment. Unrepairable spans remain rejected.
- Direct evidence keeps a fixed total budget but reserves positions for dependency-paper, source-block,
  Claim-semantic, and endpoint retrieval signals.
- State mapping combines concept similarity with exact, directional, or categorical state compatibility.
- A Claim found outside the initial Context shortlist has its own Context scored before Claim gating;
  Context gating is not bypassed.

## Indexing recall correction

`CKGQ0011` failed because P000040 SourceBlock `P000040:S03:P0039` was present in the Claim prompt but
its September explanation was folded into a general rainfall Claim. Large Claim bundles are now split
deterministically without dropping SourceBlocks. Each call receives only the target Context lineage
and compact available Facets. The prompt reads once for outcomes and once for supported explanations.

The corrected extraction returns a separate `AUTHORS_INTERPRETATION_OF_OWN_RESULT` Claim stating that
land-atmosphere feedback is strongest in September because post-JJA soil moisture is widespread and
Kharif crops are mature. Its sole evidence block is `P000040:S03:P0039`.

## Targeted results

- `CKGQ0007`: retrieved the opposite El Nino and La Nina rainfall/soil-moisture responses.
- `CKGQ0026`: recovered the approximately 0.5 K mid-latitude cooling and approximately 1 K northern
  Canada warming findings that aggregate top-eight selection had omitted.
- `CKGQ0033`: constructed the supported forest-to-crop conversion -> evapotranspiration decrease ->
  convective-instability decrease -> moderate-rainfall decrease path. This is scientifically supported,
  but it does not fully recover the benchmark's roughness -> wind -> moisture-convergence route. The
  indexed paper has the first three edges of that route, while the final extracted Claim combines
  convective instability and moisture convergence into prose under a single convective-instability
  source endpoint. This is a remaining Claim-atomicity issue, not a query-planning failure.
- `CKGQ0011`: after the indexing correction, answers that September maximization is caused by high
  post-JJA soil moisture and mature crop conditions, citing P000040.

The 20-question rerun completed 18 questions. Both failures were operational: `CKGQ0005` reached Earth
Engine without the main repository's `.env` being visible from the experiment worktree, and
`CKGQ0015` encountered a refused local Ollama connection. Across the 18 completed questions:

- expected-paper retrieval: 18/18;
- mean / median reference-token F1: 0.3572 / 0.3813;
- mean / median latency: 97.4 / 80.1 seconds.

The previous completed 20-query run had expected-paper retrieval of 17/20, mean / median F1 of
0.3217 / 0.3316, and mean / median latency of 111.0 / 76.0 seconds. The new completed subset therefore
shows higher evidence recall and answer overlap, while median latency is slightly higher. It is not a
strict 20-versus-20 comparison because the two operational failures must be rerun unchanged.

The rerun is stored under `climatekg/runtime/outputs/apv1_20_final/`. Exact-span warnings remain
explicit; generated ellipsis spans are normalized only when one continuous segment is copied exactly
from the question. The final normalization and collective-contrast cleanup passed deterministic tests,
but their targeted live rerun was blocked when stale Ollama server processes exhausted GPU memory. No
model or context-window fallback was used.

## Artifacts

- Corrected graph: `climatekg/runtime/outputs/apv1/parquet_graph_atomic_plan_v1/`
- P000040 extraction test: `climatekg/runtime/outputs/apv1/p40_batch_test_compact_v2/`
- Corrected September query: `climatekg/runtime/outputs/apv1_q11_fixed_v3/`
- Twenty-query run: `climatekg/runtime/outputs/apv1_20_final/`
