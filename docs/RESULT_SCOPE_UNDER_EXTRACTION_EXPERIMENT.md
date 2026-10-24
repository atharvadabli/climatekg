# Focused Result-Scope Extraction Experiment

## Problem

The previous `P000084` run extracted five valid Claims, but all five focused on the sparse-versus-extensive deforestation comparison. SourceBlock `P000084:S09:P0057` was supplied to Claim extraction but did not produce Claims for the reported regional energy-balance mechanisms.

This was an extraction-task coverage problem. The model received one broad comparison task and 85 SourceBlocks. Findings reported within the common simulation setting, rather than as differences between the sparse and extensive schemes, had no explicit extraction focus.

## Minimal design change

The paper map now returns `result_scopes`. A result scope is a temporary extraction-planning record with:

- a concise scientific focus;
- one existing Context or Transition that owns the findings;
- the SourceBlocks that must reach that focused Claim call.

Result scopes are not graph nodes and do not alter the Context, Facet, Transition, or Claim schemas stored in the graph.

For long papers, every SourceBlock identified as a result by the section scouts must occur in at least one result scope. The check compares stable IDs only; it does not compare generated wording. Missing coverage fails visibly before Claim extraction.

Within the limited map-consolidation source budget, the selector keeps setting-name evidence and the paper overview first, then result passages, then additional setting-detail passages. This gives the mapper the scientific text needed to name and assign result scopes without dropping the evidence needed to construct the setting tree.

Claim extraction receives both the owning scope and the result focus. The owning scope determines provenance. The focus determines which family of relationships should be extracted from the supplied passages.

## Expected `P000084` coverage

At minimum, the new map should create a context-owned result scope similar to:

```json
{
  "temp_id": "R_MECHANISMS",
  "label": "regional local and nonlocal energy-balance mechanisms",
  "scope_type": "context",
  "scope_temp_id": "<common MPI-ESM setting ID>",
  "claim_seed_block_ids": ["P000084:S09:P0057"]
}
```

This is an acceptance example, not generated output. The model may use different concise wording.

The resulting atomic Claims should preserve at least:

1. In the humid tropics, the local surface-temperature response is dominated by latent-heat-flux changes.
2. The paper interprets those latent-heat changes as probably triggered by changes in evapotranspiration efficiency. The uncertainty expressed by “probably” must remain.
3. North of 40 degrees N, albedo-driven reduction in net shortwave radiation partly produces local cooling, especially with snow.
4. For nonlocal tropical effects, latent- and sensible-heat changes indicate a southward shift of tropical rainbands.
5. Increased shortwave and decreased longwave net radiation are interpreted as indicating reduced atmospheric water vapor and cloud cover.

The humid tropics, north-of-40-degrees, snow-affected, local, and nonlocal distinctions should be represented as conditioning Facets when they define applicability, or as Claim analysis cases when they are reported subsets of an unchanged simulation. They must not be encoded as mechanism Facets.

## Files changed

- `climatekg/extraction_models.py`: extraction-only `MapResultScope` schema.
- `climatekg/extract.py`: stable-ID coverage check and one Claim task per result scope.
- `prompts/paper_map.txt`: standalone result-scope planning instructions.
- `prompts/map_consolidation.txt`: requires coverage of every scouted result block.
- `prompts/claim_extraction.txt`: explains target ownership separately from result focus.
- `land_atmosphere_kg_indexing_pipeline.md`: normative behavior and prompt versions.

## Validation status

Deterministic and prompt tests:

```text
48 passed, 1 environment-dependent test deselected
```

Repository test run:

```text
119 passed, 1 deselected, 5 setup errors
```

The five errors are existing Windows temporary-directory permission failures before test execution. No executed test failed.

The live `P000084` replay is stored under:

```text
climatekg/runtime/outputs/result_scope_p84_v1/
```

Nemotron parsing, cleaning, and SourceBlock generation completed. The replay stopped at the first Qwen section-scout request because Ollama could not allocate a 15,507,660,800-byte CUDA buffer for `qwen3.6:27b`. The same failure occurred at 32K and 16K request contexts. No alternative model or CPU fallback was used, so no new scientific extraction result is claimed yet.

## Adoption criteria

Do not merge this experiment based only on `P000084`. Resume the replay when Qwen can load, then require:

- `P000084:S09:P0057` appears in a result scope;
- the humid-tropics latent-heat mechanism is extracted with correct evidence;
- the previous five valid Claims remain represented;
- no unsupported mechanisms are introduced;
- regression papers retain their previously verified Contexts and Claims;
- Claim recall improves without an unacceptable increase in LLM calls or elapsed time.
