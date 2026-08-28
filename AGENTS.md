# Project

This repository implements a land-atmosphere scientific Knowledge Graph / GraphRAG system for context-conditioned reasoning about land-use and land-cover impacts on weather and climate.

Before coding, read:

- `land_atmosphere_kg_problem_statement.md` - project purpose and intended behavior.
- `land_atmosphere_kg_indexing_pipeline.md` - authoritative indexing implementation specification.
- `land_atmosphere_kg_query_pipeline.md` - authoritative query implementation specification.
- `land_atmosphere_kg_project_summary.md` - supporting architectural context.

The indexing and query pipeline files are normative. If implementation behavior conflicts with them, the specification wins.

# Implementation Rules

- Implement the specified schemas, algorithms, prompts, thresholds, fallbacks, and boundary-case behavior faithfully.
- Do not redesign the graph schema, extraction objects, retrieval logic, similarity formulas, or query flow unless the specifications are internally inconsistent or impossible to implement.
- If an ambiguity remains, choose the smallest implementation consistent with the specifications and document the decision in code comments or an implementation note.
- Prefer deterministic Python for operations that can be expressed algorithmically. Do not delegate deterministic logic to an LLM.
- Use the LLM only where the specifications explicitly require semantic judgment, extraction, reconciliation, classification, or synthesis.
- Preserve intermediate artifacts and JSON outputs for every major indexing and query stage so failures can be traced precisely.
- Keep functions modular and testable. Avoid hidden state and implicit transformations.
- Validate structured LLM outputs against schemas before downstream use.

# LLM Configuration

Primary local generative model:

`ollama qwen3.6:27b`

Use the reasoning/thinking level specified for each pipeline stage. Prefer no, low, or medium reasoning so requests stay comfortably within the available context window. Do not silently escalate to heavier reasoning unless a stage explicitly requires it or a test demonstrates that it is necessary.

Prompts should be versioned in code or configuration and should match the wording and output schemas defined in the implementation specifications.

# Scientific Extraction Invariants

- Every extracted scientific object must retain provenance to the exact supporting SourceBlock or derived-data provenance defined by the specs.
- Evidence IDs must refer to the smallest sufficient directly supporting evidence set, not every block shown to the model.
- Never convert cited background literature into a finding of the current paper.
- Do not invent intermediate mechanisms that are not supported by evidence.
- Preserve null, contradictory, conditional, scale-dependent, seasonal, spatial, and sign-reversing findings.
- Split Contexts when the specification requires scientifically distinct regimes; do not encode major reversals only as prose qualifiers.
- `Facet.domain` is controlled vocabulary; `Facet.notion` and `Facet.description` remain semantically open as specified.
- Do not over-normalize Facet vocabulary.
- Normalize vocabulary only where identity matters for graph connectivity, especially canonical States/concepts.
- Embedding similarity may propose merge candidates but must not silently force uncertain semantic merges.
- `Claim.conditioning_facet_ids` should reference only Facets that materially condition transfer/applicability of that Claim, not every Facet in the Context.

# Query Invariants

- Missing context information is not the same as contextual mismatch.
- Keep context similarity, coverage, intervention similarity, spatial-configuration relevance, and mechanism relevance distinguishable in intermediate reports.
- Retrieval/applicability scores are ranking signals, not probabilities that a scientific Claim is true.
- Context gating must happen before mechanism-path construction.
- Do not create mechanism paths by combining Claims from environmentally incompatible supporting Contexts.
- Preserve the distinction between causal and associative Claims.
- Final answers must be grounded in retrieved Claims and their supporting SourceBlocks.
- Every substantive scientific answer should be traceable from answer statement to mechanism path / Claim to Paper to supporting SourceBlock(s).

# Spatial Reasoning

Spatial land-atmosphere effects must follow the relation-specific algorithms in the query specification.

Do not collapse all spatial effects into generic upwind/downwind reasoning. Preserve distinctions such as:

- local advection and propagation;
- patch/edge and heterogeneity effects;
- distance-decay effects;
- windward/leeward effects;
- moisture recycling / precipitationsheds;
- remote teleconnections.

Only translate a literature relation into a real-area recommendation when both the local environmental/geometric data and transferable literature evidence support that translation. Do not invent cardinal directions from prose alone.

# Validation

After implementation, run an end-to-end validation on approximately 10 representative PDFs covering varied mechanisms and study types.

The validation should exercise:

PDF -> parsing and cleaning -> SourceBlocks -> paper mapping -> Contexts / Facets / Transitions / Claims -> consolidation -> State canonicalization -> embeddings -> Neo4j ingestion -> query parsing / enrichment -> Context and Facet similarity -> Claim gating -> mechanism-path search -> evidence retrieval -> grounded referenced answer.

For every test query, save the structured query report and relevant intermediate JSON so incorrect answers can be traced to the exact stage that produced the error.

Treat failures first as possible specification, extraction, retrieval, graph, or implementation issues rather than dismissing them as generic LLM randomness.

# Coding Style

- Prefer explicit, readable code over clever abstractions.
- Keep schema models centralized and versioned.
- Make thresholds and ranking weights configurable rather than hard-coded throughout the codebase.
- Log IDs, scores, thresholds, and rejection reasons needed to reproduce retrieval decisions.
- Add unit tests for deterministic algorithms and integration tests for each pipeline boundary.
- Do not silently recover from malformed scientific objects; reject, repair according to the specified procedure, or record the failure visibly.

# Priority Order

When instructions appear to conflict, use this priority:

1. `land_atmosphere_kg_indexing_pipeline.md` / `land_atmosphere_kg_query_pipeline.md`
2. `land_atmosphere_kg_problem_statement.md`
3. `land_atmosphere_kg_project_summary.md`
4. Existing implementation choices

Do not change scientific behavior merely to simplify implementation.
