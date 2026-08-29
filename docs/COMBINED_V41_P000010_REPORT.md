# Combined Extraction v4.1: P000010 Test

## Purpose

This experiment tests whether a single Qwen extraction call can avoid the provenance-ID and claim-scope failures observed in the earlier combined extractor without changing ClimateKG's final graph schema.

Branch: `experiment/combined-v4-constrained-refs`

Paper: `P000010`, `science.aar5629.pdf`

Runtime output:

`climatekg/runtime/outputs/combined_v41_p000010_20260829/combined/`

## Implementation

The LLM-facing extraction contract now differs from the final graph contract:

1. Cleaned non-reference SourceBlocks receive request-local handles such as `E001`.
2. The request's JSON Schema enumerates the available handles in every evidence field.
3. Facets and context-scoped Claims are nested inside their Context.
4. Transition-scoped Claims are nested inside their Transition.
5. Conditioning facets use `(context_temp_id, facet_key)` references.
6. Deterministic Python maps handles back to permanent SourceBlock IDs, assigns temporary Facet and Claim IDs, flattens the response, and runs the existing strict provenance and reachability checks.
7. The rest of indexing uses the unchanged final `Context`, `Facet`, `Transition`, and `Claim` schemas.

## Exact Artifacts

- Exact populated request: `data/P000010/extraction/small_paper/039ce325-5d05-4fa2-b327-84341027b102.attempt0.request.json`
- Raw Ollama response: `data/P000010/extraction/small_paper/039ce325-5d05-4fa2-b327-84341027b102.attempt0.json`
- Request-local handle mapping: `data/P000010/extraction/small_paper/evidence_handle_catalog.json`
- Nested schema-valid output: `data/P000010/extraction/small_paper/schema_validated.json`
- Deterministically flattened output: `data/P000010/extraction/small_paper/flattened.json`
- Strictly validated flat output: `data/P000010/extraction/small_paper/validated.json`
- Final indexed paper: `data/P000010/final/final_paper.json`
- Parquet/FAISS index: `parquet_graph/`

## Runtime

The final v4.1 run used Qwen with `think: false` and ended normally with `done_reason: stop`.

- Cleaned non-reference input: 4,508 `o200k_base` tokens
- Ollama prompt tokens: 7,657
- Ollama generated tokens: 6,246
- Whole-paper indexing time: 242.6 seconds
- Parquet/FAISS build: 0.33 seconds

## Output

- Contexts: 9
- Facets: 12
- Transitions: 5
- Claims: 17
- Canonical States: 29
- SourceBlocks: 87
- Parquet relationships: 279

All 50 supplied evidence handles were valid schema choices. The response used 16 distinct handles, and every handle mapped back to an exact permanent SourceBlock ID. Nested, flattened, and final object counts agree.

## Previously Failing 30% Case

The old response created a 30% solar-panel Context and Facet but attached its Claim to the 15%-to-45% Transition. The reachability validator correctly rejected that output.

The v4.1 response creates:

- `C4`: the common 15% solar-farm case;
- `C6`: the high-efficiency case;
- `C7`: the intermediate-efficiency 30% case;
- `T5`: the 15%-to-high-efficiency comparison.

The 30% finding is nested under `C7` and deterministically becomes a Context-scoped Claim. Its `panel_efficiency` Facet also belongs to `C7`. The 15%-to-high-efficiency comparison remains separate under `T5`.

## Prompt Adjustment During Testing

The first v4 run passed integrity checks but also stored some reported temperature and precipitation outcomes as Facets. The prompt still left enough room to interpret any reported property as a condition.

Version 4.1 states positively that a Facet defines an input or stratifying setting condition, while a reported response belongs in a Claim. On the fresh v4.1 run, Facets fell from 26 to 12 and the reported temperature and precipitation responses remained Claims. Increased surface roughness remains a Facet because it is the imposed land-surface condition defining the wind-farm setting.

## Verification

`64 passed` in the full test suite.

Added deterministic tests cover:

- stable short-handle construction and exact mapping;
- evidence-handle enums in the request JSON Schema;
- nested Context and Transition claim scoping;
- exact evidence round-tripping;
- rejection of unknown handles;
- rejection of unreachable conditioning Facets after flattening;
- standalone prompt requirements for complete setting combinations.

## Remaining Limits

This is one successful paper, not corpus validation. A model can still choose the wrong valid evidence handle, place a Claim in a scientifically wrong container, or omit a reported setting. Existing deterministic validation detects broken keys and unreachable Facets but cannot prove complete scientific coverage.

The proposed compact two-call route for structurally complex papers is not implemented in this branch. Automatic combined routing also remains disabled by default. The next meaningful test is `P000007`, whose crossed rainfed/irrigated and drought/non-drought settings directly exercise the new complete-setting hierarchy.
