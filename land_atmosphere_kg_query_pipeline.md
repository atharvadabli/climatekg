# Land–Atmosphere Knowledge Graph: Detailed Query Pipeline
## user question → query Context → applicability scoring → context-gated graph → grounded answer

**Status:** implementation-ready specification  
**Revision:** 2026-08-19 — exact query execution + field-specification pass: source-span-safe parsing, shared enrichment, State mapping, Claim/path scoring, contradiction retrieval, spatial transfer, evidence selection, grounding, calibration algorithms, and query semantic/provenance writing guidance.  
**Primary generative model:** `qwen3.6:27b` through Ollama  
**Reasoning policy:** `no` / `low` / `medium` only  
**Embedding family:** Qwen3-Embedding  
**Graph store:** Neo4j  
**Algorithmic layer:** Python  
**Design goal:** answer local and global land–atmosphere questions with context-aware, spatially aware, evidence-grounded mechanism retrieval.

---

# 1. Purpose

The query pipeline should support questions such as:

```text
What happens if forest cover is reduced here?
What interventions could reduce hot extremes here?
Could afforestation increase rainfall in this watershed?
Where should restoration be placed relative to prevailing winds?
Would an intervention act locally, downwind, or remotely?
What does the literature say globally about deforestation and rainfall?
```

The system must do more than retrieve papers. It must:

1. construct the environmental Context of the user's area;
2. retrieve literature Contexts that are environmentally analogous;
3. retrieve Claims that are applicable to that Context and relevant to the source/target question;
4. prevent graph paths assembled from incompatible study environments;
5. preserve spatial/directional information such as upwind/downwind, windward/leeward, patch scale, edge effects, and distance decay;
6. return an answer in which scientific statements are traceable to Claims, papers, and exact SourceBlocks;
7. expose the retrieval/applicability calculations as reportable JSON.

Retrieval scores are **ranking/applicability scores**, not probabilities that a scientific statement is true.

**Normative implementation note:** Sections 1–60 define the query architecture; Section 61 defines the exact executable algorithms for every previously ambiguous operation and overrides less-specific shorthand earlier in the file.

---

# 2. Core query invariants

## 2.1 Use the same Context language on both sides

Paper environments and query environments use the same representation:

```text
Context
├── SpatialSupport
└── Facets[]
```

A Query Facet has the same semantic fields as an indexed Facet:

```text
domain
notion
description
```

The query version additionally records provenance such as `user` or `derived` outside the semantic text.

There is no separate `Facet.scope`. Season, atmospheric layer, time of day, spatial scale, and similar qualifiers belong naturally in the Facet description. If the user explicitly asks about a genuinely different scenario/season, it may be represented as a separate query Context variant.

---

## 2.2 Do not hallucinate environment from geographic names

If the user says:

```text
"my watershed in Rajasthan"
```

the parser may record the place name, but must not invent:

```text
semi-arid
monsoonal
southwesterly winds
low soil moisture
```

Those facts must come from explicit user input or deterministic enrichment datasets.

---

## 2.3 Missing is not mismatch

If a query contains a soil-moisture Facet and a paper Context contains no hydrology Facet, record this as **missing/unknown coverage**, not as a semantic contradiction.

Context reports therefore keep separate:

```text
semantic similarity
coverage
missing query facets/domains
actual low-similarity matches
```

---

## 2.4 Environmental applicability and intervention similarity are separate

A study can have:

```text
high environmental analogy + different intervention
```

or:

```text
same intervention + poor environmental analogy
```

Do not collapse these into one embedding.

Keep separate retrieval channels for:

```text
Context similarity
source/target State relevance
Transition/intervention similarity
Claim/mechanism relevance
spatial-configuration similarity
```

They may be combined only in later ranking.

---

## 2.5 Context gate before graph traversal

Correct order:

```text
Query Context
   ↓
retrieve/rerank applicable Contexts
   ↓
collect applicable Claims
   ↓
build query-specific subgraph
   ↓
search paths
```

Never search arbitrary global paths first and check Context afterward.

---

## 2.6 Every substantive scientific answer must be grounded

The final chain is:

```text
answer statement
→ selected path/Claim(s)
→ Paper
→ exact SourceBlock(s)
```

Query-area derived facts additionally point to their enrichment source and method.

---

# 3. Minimal Query schema

Keep the semantic schema small.

```json
{
  "query_id": "Q000001",
  "mode": "forward | backward | a_to_b | global",
  "context": {},
  "source": {
    "concept": "forest cover",
    "state": "decrease"
  },
  "target": {
    "concept": "precipitation",
    "state": "increase"
  },
  "intervention_description": "Remove approximately 20% of forest cover from the watershed."
}
```

`source`, `target`, and `intervention_description` are optional depending on the query.

Do not create a large query ontology.

---

# 4. Query Context schema

```json
{
  "spatial_support": {
    "kind": "watershed",
    "name": "user watershed",
    "geometry": null,
    "enrichable_study_location_name": null,
    "resolution": "exact"
  },
  "facets": [
    {
      "id": "Q000001_F001",
      "domain": "atmosphere",
      "notion": "seasonal background wind regime",
      "description": "During the wet season, low-level flow is predominantly southwesterly and directionally persistent; dry-season flow is weaker and more variable.",
      "origin": "derived",
      "source": {
        "dataset": "ERA5",
        "version": "configured-version",
        "method": "configured seasonal wind enrichment"
      }
    }
  ]
}
```

Allowed domains are identical to indexing:

```text
spatial_configuration
land_surface
hydrology
atmosphere
climate
substrate_terrain
other
```

Query `origin`:

```text
user
provided_dataset
derived
```

The semantic embedding text does not include `origin`; provenance is retained for reporting.

---


## 4.1 Query field-writing specifications

Use the same semantic writing conventions as indexing so query and paper representations remain comparable.

| Query field | Writing specification |
|---|---|
| `source.concept`, `target.concept` | Usually **1–8 words**; compact scientific noun phrase representing identity only. |
| `source.state`, `target.state` | Usually **1–5 words**; compact directional/categorical state. Preserve detailed magnitude, location, timing, and spatial arrangement elsewhere. |
| `intervention_description` | Usually **10–60 words** when present. Preserve all intervention detail explicitly supplied by the user: magnitude, replacement type, timing, orientation, location, patch arrangement, etc. Never add scientific consequences or unstated environmental facts. Shorter is valid for simple interventions. |
| Query Facet `notion` | Usually **2–8 words**, using the same open-vocabulary notion style as indexed Facets. |
| Query Facet `description` | Usually **20–60 words** for enriched/normalized Facets, but may be shorter when the user supplied only a simple fact. Preserve the known state without padding. |
| `supporting_text_span` | Exact substring of the user question after Unicode normalization; never paraphrased. |
| `spatial_reference.text` | Preserve the user's literal location/identifier wording. |
| `ambiguities[]` | Short machine-readable notes about unresolved semantic/spatial ambiguity; do not place scientific guesses here. |
| Query Facet `source` | Provenance only. For derived/provided-dataset Facets record dataset/product, version where available, method/algorithm version, temporal window, and target geometry/object. Do not place provenance text into the semantic description solely for traceability. |

These are soft targets, never hard validators. Missing information must remain missing rather than being filled to make a field more descriptive.

# 5. Determine query mode

Prefer deterministic mode assignment after parsing source and target.

```python
if explicit_global_request:
    mode = "global"
elif source is not None and target is not None:
    mode = "a_to_b"
elif source is not None:
    mode = "forward"
elif target is not None:
    mode = "backward"
else:
    mode = "global"
```

Examples:

```text
"What happens if irrigation expands?"         → forward
"What could reduce hot extremes?"             → backward
"Could irrigation reduce hot extremes?"       → a_to_b
"How does deforestation affect climate globally?" → global
```

When a question asks how one source changes two or more outcomes joined by `and`, keep the source, preserve the requested outcomes in `intervention_description`, leave `target=null`, and use `forward` mode. One target object represents one graph endpoint; a combined target would require a nonexistent compound State and suppress otherwise valid direct paths.

`global` means the answer is not gated to one query environment. Source and target may still be populated.

---

# 6. Configuration

Keep all query parameters in one versioned configuration.

```yaml
ollama:
  model: "qwen3.6:27b"
  structured_output: true
  stages:
    query_parse: {temperature: 0.0, thinking: no}
    final_synthesis: {temperature: 0.0, thinking: low}
    final_synthesis_complex: {temperature: 0.0, thinking: medium}

embeddings:
  model: "Qwen3-Embedding"
  dimension: 2048
  normalize: true

state_mapping:
  top_k: 5
  seed_top_k: 5
  candidate_margin: 0.05

context_retrieval:
  ann_top_k: 100
  rerank_top_k: 30
  notion_weight_alpha: 0.35
  missing_coverage_penalty_lambda: 0.25
  domain_weights:
    spatial_configuration: 1.0
    land_surface: 1.0
    hydrology: 1.0
    atmosphere: 1.0
    climate: 1.0
    substrate_terrain: 1.0
    other: 0.5
  min_context_score: null

conditioning:
  weight_beta: 0.25
  min_known_conditioning_score: null

mechanism_retrieval:
  claim_semantic_top_k: 100
  transition_top_k: 50
  candidate_claim_top_k: 200

claim_ranking:
  weights:
    context: 0.45
    mechanism: 0.20
    intervention: 0.15
    endpoint: 0.20

path_search:
  max_path_length: 4
  beam_width: 40
  max_paths: 20
  cross_edge_context_threshold: null
  path_length_penalty: 0.08

synthesis:
  top_paths: 8
  max_claims: 24
  max_source_blocks_per_claim: 2
  evidence_input_budget_tokens: 16000
  hard_llm_input_budget_tokens: 20000

spatial:
  directional_persistence_threshold: 0.55
  spatial_transfer_min_score: null
  sector_quantile: 0.33
  terrain_barrier_relief_m: 300
  terrain_barrier_search_km: 50
  terrain_barrier_min_fraction: 0.5

contradictions:
  per_focal_claim_top_k: 3

evidence_selection:
  direct_weight: 0.7
  query_weight: 0.3
  results_section_bonus: 0.05
  discussion_section_bonus: 0.02
```

The numerical values above are **starting points**, not scientific constants. Hard similarity thresholds should remain `null` until benchmark queries calibrate them.

---

# 7. Stage 1 — parse the user query

Use one small structured-output call.

Recommended:

```text
model = qwen3.6:27b
thinking = no
temperature = 0
```

## Prompt: `query_parse.txt`

```text
SYSTEM

Parse a land-atmosphere user question into a minimal retrieval request.

Return only information stated by the user. Do not add environmental,
geographic, climatic, hydrologic, terrain, wind, soil, or land-cover
facts from your own knowledge.

Tasks:
1. identify an optional source State {concept, state};
2. identify an optional target State {concept, state};
3. preserve a rich intervention description when the question specifies
   magnitude, replacement type, spatial arrangement, direction, timing, or
   location of a land-use change; usually keep this to 10–60 words, but never
   omit user-supplied detail or pad a simple intervention;
4. extract explicit environmental/context statements as rich Facets;
5. record the user's location text or supplied spatial identifier without
   inferring environmental properties;
6. for every extracted endpoint and explicit Context Facet, return an exact
   supporting_text_span copied from the user question;
7. detect whether a global/non-location-conditioned synthesis is requested.

Facet domains:
- spatial_configuration
- land_surface
- hydrology
- atmosphere
- climate
- substrate_terrain
- other

Rules:
- no confidence scores;
- no invented mechanisms;
- no invented coordinates;
- no scientific answer yet;
- use compact endpoint concepts (usually 1–8 words) and compact
  directional/categorical states (usually 1–5 words);
- use short Facet notions (usually 2–8 words) and evidence-faithful Facet
  descriptions; 20–60 words is a soft target for rich Facets, never a reason
  to invent or pad information;
- preserve important intervention detail in intervention_description;
- return schema-valid JSON only.

USER

{user_question}
```

## Parser output

```json
{
  "source": {"concept": "forest cover", "state": "decrease", "supporting_text_span": "Reduce forest cover"},
  "target": {"concept": "precipitation", "state": "increase", "supporting_text_span": "precipitation"},
  "intervention_description": "Reduce forest cover by 20%, preferentially on the western side of the watershed.",
  "explicit_context_facets": [],
  "spatial_reference": {
    "text": "watershed W123",
    "kind_hint": "watershed"
  },
  "global_requested": false,
  "ambiguities": []
}
```

---

# 8. Stage 2 — resolve SpatialSupport

Resolution is deterministic/application-specific.

Possible inputs:

```text
watershed ID
lat/lon
polygon/GeoJSON
saved planning area
named place
no location
```

Rules:

- never invent geometry;
- if an application registry maps a watershed ID to a polygon, use it;
- if a named location can only be resolved approximately, record that resolution;
- if no reliable geometry exists, keep `geometry=null`;
- global queries do not require SpatialSupport.

---

# 9. Stage 3 — build the sparse Query Context

Start only from explicit user information.

Example:

```text
User:
"Could increasing tree cover reduce daytime heat in this irrigated watershed?"
```

Initial Facets may be only:

```json
[
  {
    "domain": "land_surface",
    "notion": "irrigated land-use setting",
    "description": "The target watershed is described by the user as irrigated.",
    "origin": "user"
  }
]
```

Sparse Context is valid.

When creating Query Facets, use the same field-writing rules as indexed
Facets: concise 2–8 word notions and normally 20–60 word rich descriptions
for derived/enriched conditions. User-stated Facets may be shorter; never pad
them or add unstated detail.

---

# 10. Stage 4 — optional query-area enrichment

Run the same deterministic enrichment families used during indexing wherever possible.

Suggested families:

```text
climate regime
hydroclimatic/aridity regime
seasonal atmospheric/wind regime
land-surface state
terrain setting
spatial configuration
```

Raw datasets may use many numerical variables internally. Their query-facing output should remain a small number of coherent descriptive Facets.

Do not produce hundreds of one-variable Facets.

---

# 11. Spatial/directional enrichment

This is essential for questions asking **what, where, or in which direction** land-use change should occur.

Possible derived Facets include:

```text
seasonal background wind regime
upwind land-cover composition
downwind land-cover composition
orientation of major LULC boundaries relative to flow
patch-size / heterogeneity regime
terrain-flow exposure
source-to-target moisture pathway
```

Example:

```json
{
  "domain": "spatial_configuration",
  "notion": "upwind land-cover composition relative to wet-season flow",
  "description": "For the dominant wet-season flow, the southwest/upwind sector of the watershed and its immediate buffer contains fragmented cropland and remnant woody vegetation, while the northeast/downwind sector is more continuously cultivated.",
  "origin": "derived"
}
```

The enrichment code creates the description from explicit geometry/raster/wind calculations. The LLM does not invent it.

---

# 12. Direction convention

Be explicit to avoid the common wind-direction error.

Meteorological wind direction usually describes **where wind comes from**.

If:

```text
wind_from = southwest
```

then air movement is toward the northeast.

For deterministic geometry:

```text
wind_to_vector = direction(wind_from + 180°)
```

For each pixel/point `x` relative to reference centroid `μ`:

```text
r(x) = dot(x - μ, wind_to_vector)
```

Within a target polygon:

```text
low r  → upwind side
high r → downwind side
```

With `sector_quantile = 0.33`:

```text
bottom third → upwind sector
middle third → crosswind/interior sector
top third    → downwind sector
```

For a buffer outside a target area, select negative/positive projection regions relative to the target and flow vector.

If seasonal directional persistence is below the configured threshold, do **not** issue one fixed upwind/downwind placement recommendation. Preserve the variable/reversing wind regime in the Facet and answer conditionally by season/regime.

---

# 13. Windward/leeward handling

`upwind/downwind` is defined relative to atmospheric flow.

`windward/leeward` is additionally terrain-relative.

Use windward/leeward only when a deterministic DEM/topographic procedure identifies a relevant ridge/barrier/exposure relationship. Otherwise do not use those terms merely because prevailing wind is known.

---

# 14. Stage 5 — map query source/target to canonical States

Do not ask the generative LLM to perform graph canonicalization.

For each endpoint:

1. deterministic normalization;
2. exact alias lookup;
3. Qwen State/concept embedding retrieval;
4. filter/score by endpoint state direction;
5. retain top candidates rather than force a merge when ambiguous.

Example report:

```json
{
  "query_endpoint": {
    "concept": "tree cover",
    "state": "increase"
  },
  "candidates": [
    {
      "state_id": "state::forest_cover::increase",
      "concept_similarity": 0.91,
      "state_compatible": true,
      "mapping_score": 0.91
    },
    {
      "state_id": "state::vegetation_fraction::increase",
      "concept_similarity": 0.84,
      "state_compatible": true,
      "mapping_score": 0.84
    }
  ]
}
```

Use `seed_top_k` candidates when mapping is genuinely ambiguous.

---

# 15. Stage 6 — create query embeddings

Create:

```text
Query Facet notion embeddings
Query Facet content embeddings
whole Query Context embedding
query intervention embedding, if present
query endpoint concept embeddings
optional full-question/claim retrieval embedding
```

Facet notion text:

```text
{domain} | {notion}
```

Facet content text:

```text
Domain: {domain}
Notion: {notion}
Description: {description}
```

Whole Context text should use the same deterministic formatting as indexed Context embeddings.

---

# 16. Stage 7 — coarse Context ANN retrieval

For a location-conditioned query:

```text
QueryContext.retrieval_embedding
        ↓
Neo4j Context vector index
        ↓
ANN top K candidate Contexts
```

Initial:

```text
ann_top_k = 100
```

This is only candidate generation. Whole-context cosine is not the final applicability score.

For a global query, skip mandatory context gating and retrieve by source/target/Claim/Transition relevance instead. Global answers should still stratify findings by study Context where useful.

---

# 17. Stage 8 — effective indexed Context reconstruction

For each candidate Context:

1. traverse ancestors root → child;
2. collect inherited + local Facets;
3. never mutate stored Facets;
4. group by domain;
5. retain each Facet's provenance.

Transition-scoped Claims preserve FROM and TO Contexts separately.

---

# 18. Stage 9 — Facet pair similarity

For query Facet `q` and candidate Facet `c` in the **same domain**:

```text
notion_cos  = cosine(q.notion_embedding, c.notion_embedding)
content_cos = cosine(q.content_embedding, c.content_embedding)
```

For reporting, clamp negative cosine to zero:

```text
n = max(0, notion_cos)
x = max(0, content_cos)
```

Then:

```text
pair_score = α*n + (1-α)*x
```

Initial:

```text
α = 0.35
```

Interpretation:

- notion similarity asks whether the two Facets concern the same scientific idea;
- content similarity asks whether the actual environmental states are similar.

---

# 19. Stage 10 — domain-wise MaxSim

For each query Facet, find its best candidate Facet **within the same domain**.

For domain `d`:

```text
S_d(Q,C)
  = mean over q in Q_d of max over c in C_d pair_score(q,c)
```

If `Q_d` exists but `C_d` is empty:

```text
domain_status = "missing_in_candidate"
```

Do not manufacture a match across domains.

---

# 20. Semantic similarity and coverage

Keep two values.

## 20.1 Semantic similarity

Weighted mean across query domains for which the candidate has at least one comparable Facet:

```text
S_semantic
```

## 20.2 Coverage

```text
coverage
 = sum(weights of query domains with candidate information)
   / sum(weights of query domains present in query)
```

## 20.3 Ranking score

A conservative but non-destructive missing-information adjustment:

```text
S_context
 = S_semantic * (1 - λ_missing * (1 - coverage))
```

where:

```text
0 <= λ_missing <= 1
```

Initial:

```text
λ_missing = 0.25
```

So missing information slightly reduces rank without being treated as a scientific mismatch.

Benchmark this parameter.

---

# 21. Required Context-similarity JSON

Every reranked Context should produce a reportable object.

```json
{
  "context_id": "P000123_C001",
  "paper_id": "P000123",
  "coarse_ann_score": 0.78,
  "context_similarity": {
    "semantic_similarity": 0.84,
    "coverage": 0.83,
    "overall_score": 0.80,
    "alpha": 0.35,
    "missing_coverage_penalty_lambda": 0.25,
    "domain_scores": {
      "climate": {
        "score": 0.88,
        "status": "matched"
      },
      "atmosphere": {
        "score": 0.82,
        "status": "matched"
      },
      "hydrology": {
        "score": null,
        "status": "missing_in_candidate"
      },
      "spatial_configuration": {
        "score": 0.73,
        "status": "matched"
      }
    },
    "facet_matches": [
      {
        "query_facet_id": "Q000001_F003",
        "candidate_facet_id": "P000123_F018",
        "domain": "atmosphere",
        "notion_similarity": 0.90,
        "content_similarity": 0.78,
        "pair_score": 0.82
      }
    ],
    "missing_query_facets": ["Q000001_F006"]
  }
}
```

This object is part of the query audit artifact and may be exposed by the UI/API.

---

# 22. Stage 11 — use Claim conditioning Facets

An indexed Claim may have:

```text
(Claim)-[:CONDITIONED_BY]->(Facet)
```

These are **not** separate Claim Facets. They are ordinary Context Facets that the paper specifically identifies as material to that Claim.

For each conditioning Facet `f_c`:

1. find Query Facets in the same domain;
2. take the best Facet pair match;
3. if the query has no information in that domain, mark it `unknown_in_query`;
4. never force a cross-domain match.

Compute:

```text
S_conditioning = mean(known conditioning matches)
```

If none are known:

```text
S_conditioning = null
```

Initial Claim applicability:

```text
if S_conditioning is null:
    A_claim = S_context
else:
    A_claim = (1-β)*S_context + β*S_conditioning
```

Initial:

```text
β = 0.25
```

Do not initially hard-reject a Claim because a conditioning Facet is unknown. Hard thresholds can be benchmarked later.

---

# 23. Conditioning match JSON

```json
{
  "claim_id": "P000123_CL018",
  "conditioning_facets": [
    {
      "candidate_facet_id": "P000123_F021",
      "domain": "atmosphere",
      "notion": "background wind regime",
      "best_query_facet_id": "Q000001_F003",
      "score": 0.86,
      "status": "matched"
    },
    {
      "candidate_facet_id": "P000123_F024",
      "domain": "hydrology",
      "notion": "antecedent soil-moisture regime",
      "best_query_facet_id": null,
      "score": null,
      "status": "unknown_in_query"
    }
  ],
  "conditioning_similarity": 0.86,
  "known_conditioning_coverage": 0.5
}
```

---

# 24. Stage 12 — Transition/intervention similarity

For a Transition-scoped Claim, do **not** blend FROM and TO Contexts into one context vector.

Use:

```text
baseline environmental applicability
    = ContextSimilarity(QueryContext, Effective(FROM Context))

intervention similarity
    = similarity(query intervention/source description,
                 indexed Transition embedding)
```

The Transition description preserves magnitude, replacement type, configuration, etc.

Example:

```text
query: 20% forest removal, concentrated in upwind sector
paper: 30% forest replaced by pasture across model domain
```

Environmental similarity and intervention similarity remain separately reportable.

---

# 25. Stage 13 — candidate Claim generation

Create a union of Claims from several channels:

```text
A. Claims scoped to top reranked Contexts/Transitions
B. Claims incident to mapped source State candidates
C. Claims incident to mapped target State candidates
D. semantic Claim embedding retrieval
E. Transition/intervention retrieval when intervention_description exists
```

Deduplicate by `claim_id`.

Then attach:

```text
context applicability
conditioning-Facet match
source/target relevance
intervention similarity
Claim semantic similarity
provenance
```

Use `candidate_claim_top_k` only after the union is scored.

---

# 26. Claim ranking components

Keep component scores visible rather than hiding everything behind one opaque number.

Possible ranking combination:

```text
R_claim
 = w_context      * A_claim
 + w_mechanism    * S_claim_semantic
 + w_intervention * S_transition
 + w_endpoint     * S_endpoint
```

Only include components that exist for that query.

Renormalize weights across present components.

Do not call this `confidence`.

The main scientific gate remains Context applicability.

---

# 27. Context gating policy

MVP recommendation:

- rerank a fixed top-K Context set;
- keep scores and score distributions;
- avoid a hard `min_context_score` until benchmark calibration;
- if a threshold is later enabled, retain a fallback minimum number of candidates so sparse queries do not return nothing.

If a query has **no environmental Context**:

```text
context gate = disabled
```

but evidence is grouped/stratified by study Context in the answer.

---

# 28. Stage 14 — build the query-specific subgraph

Create an in-memory or temporary logical view containing only candidate Claims and their State endpoints.

```text
State ← Claim → State
```

Do not alter the persistent graph.

Each Claim carries its applicability/report object.

---

# 29. Stage 15 — graph traversal by query mode

## Forward

Start from source State candidates and traverse outward.

```text
A → ?
```

## Backward

Start from target State candidates and traverse Claims in reverse.

```text
? → B
```

## A→B

Search paths from source State candidates to target State candidates.

## Global

Use source/target constraints if supplied, but do not condition on one query Context. Group mechanisms by study Context/regime rather than pretending one universal effect exists.

---

# 30. Path length

Initial:

```text
max_path_length = 4 Claims
```

Why:

- most useful mechanism explanations should be short;
- longer paths create more opportunities for context incompatibility;
- longer chains are harder to ground and synthesize safely.

This is tunable.

---

# 31. Cross-edge Context coherence

A path should not combine individually relevant Claims from mutually incompatible paper Contexts.

For adjacent Claims supported by Contexts `C_i` and `C_j`, calculate a symmetric Context similarity:

```text
S_sym(C_i,C_j)
 = 0.5 * [S(C_i,C_j) + S(C_j,C_i)]
```

Use the same Facet/domain machinery, with indexed Context `C_i` temporarily treated as the query set for one direction.

Path coherence:

```text
C_path = min adjacent S_sym
```

This catches the classic Frankenstein path:

```text
Amazon → Great Plains → Sahel → generic LES
```

If `cross_edge_context_threshold` is configured, reject paths whose `C_path` falls below it.

Initially keep the threshold null and rank by coherence until calibrated.

---

# 32. Path applicability and ranking

Conservative Context applicability:

```text
A_path = min(A_claim for claim in path)
```

This makes the weakest transfer step visible.

Example path rank:

```text
length_factor = 1 / (1 + λ_len * (path_length - 1))

R_path
 = A_path
   * C_path
   * mean(claim_relevance_scores)
   * length_factor
```

If there is only one Claim, set:

```text
C_path = 1
```

Keep all component scores in the report.

This is a retrieval ranking formula, not a scientific probability.

---

# 33. Beam search

For larger candidate subgraphs, use bounded beam search.

Initial:

```text
beam_width = 40
max_paths = 20
```

At each expansion:

1. reject repeated-State loops unless explicitly allowed;
2. reject Claim reuse;
3. update minimum Claim applicability;
4. update cross-edge Context coherence;
5. apply max-path-length bound;
6. retain top beam candidates by partial path score.

---

# 34. Contradictory and alternative evidence

After selecting leading paths, deliberately search for:

```text
same/similar source concept
same/similar target concept
opposite target/source state
null-effect Claims
alternative mechanisms
```

Score their Context applicability to the query.

Do not hide contradictions because they score slightly below the top path.

The final answer should distinguish:

```text
consistent evidence
context-dependent differences
opposite findings
unknown transferability
```

---

# 35. Spatial evidence retrieval

If the user's question asks:

```text
where?
which side?
upwind or downwind?
how large a patch?
near an edge?
how far away?
```

boost/select evidence with relevant `spatial_configuration` Facets and Claims whose descriptions contain spatial relations.

Important notions may include:

```text
upwind land-cover composition
downwind response
windward/leeward exposure
patch-induced circulation
heterogeneity scale
edge-triggered convection
distance-decay
remote moisture source / precipitationshed
teleconnection
```

Spatial relevance is still conditioned by atmosphere/climate/hydrology; it is not a standalone keyword search.

---

# 36. Translating literature spatial relations to the user's geography

The literature supplies the **relation**:

```text
upwind forest matters
storm initiation occurs near dry/wet gradients
effect decays within tens of kilometres
patch scale modifies circulation
```

The query enrichment supplies the **local geometry**:

```text
which side is upwind this season
where current forest/cropland patches lie
where the target settlement/crop area lies
terrain exposure
```

Only combine them when both are available.

Example logic:

```python
if selected_evidence_supports("upwind intervention") \
   and query_has_reliable_wind_vector \
   and spatial_context_match_is_adequate:
    translate upwind relation to query polygon sectors
else:
    do not name a geographic side
```

The system must never invent "west", "southwest", etc. solely from the paper.

---

# 37. Scale transfer rule

Do not directly convert a paper's spatial scale into a planning prescription without checking compatibility.

Examples that need explicit reporting:

```text
LES patch scale vs real watershed scale
local 10–40 km heterogeneity vs continental moisture recycling
50 km temperature distance-decay vs teleconnection-scale rainfall effects
```

A useful answer may say:

```text
"The evidence supports an upwind/downwind mechanism, but the studied patch scale differs from your watershed, so exact placement distance is not established."
```

This is preferable to false precision.

---

# 38. Stage 16 — select evidence SourceBlocks

For each selected Claim:

1. load exact supporting SourceBlocks;
2. score blocks for direct support to the Claim and query;
3. take at most `max_source_blocks_per_claim`;
4. preserve page/section/source IDs;
5. do not feed entire papers to final synthesis.

Also include relevant Context/Facet evidence blocks when the answer depends on a transfer condition not stated in the Claim block itself.

---

# 39. Query audit/report JSON

Every query should write a reproducible artifact such as:

```text
queries/Q000001/query_report.json
```

Top-level shape:

```json
{
  "query": {},
  "config_version": "query-v0.1",
  "query_context": {},
  "state_mapping": {},
  "context_matches": [],
  "claim_matches": [],
  "paths": [],
  "contradictory_evidence": [],
  "selected_source_blocks": [],
  "answer": {},
  "timings": {},
  "warnings": []
}
```

This is the object that can be reported/debugged externally.

---

# 40. Context match report example

```json
{
  "context_id": "P0042_C003",
  "paper_id": "P0042",
  "scores": {
    "coarse_context_cosine": 0.76,
    "semantic_context_similarity": 0.85,
    "context_coverage": 0.83,
    "context_overall": 0.81
  },
  "domain_scores": {
    "atmosphere": 0.87,
    "climate": 0.89,
    "hydrology": null,
    "spatial_configuration": 0.72
  },
  "facet_matches": [
    {
      "query_facet_id": "Q0001_F4",
      "paper_facet_id": "P0042_F17",
      "notion_cosine": 0.92,
      "content_cosine": 0.84,
      "pair_score": 0.87
    }
  ],
  "missing": [
    {
      "query_facet_id": "Q0001_F7",
      "reason": "candidate has no hydrology Facet"
    }
  ]
}
```

The UI can show this as "why this study matched".

---

# 41. Claim match report example

```json
{
  "claim_id": "P0042_CL09",
  "scope_id": "P0042_T02",
  "from_state_id": "state::soil_moisture::heterogeneous",
  "to_state_id": "state::convective_initiation::increase",
  "scores": {
    "context_applicability": 0.81,
    "conditioning_similarity": 0.86,
    "intervention_similarity": 0.74,
    "claim_semantic_similarity": 0.83,
    "ranking_score": 0.81
  },
  "conditioning_matches": [],
  "source_block_ids": [
    "P0042:S04:P0033"
  ]
}
```

---

# 42. Path report example

```json
{
  "path_id": "PATH_003",
  "claim_ids": [
    "P0012_CL04",
    "P0042_CL09",
    "P0051_CL02"
  ],
  "state_ids": [
    "state::forest_cover::decrease",
    "state::evapotranspiration::decrease",
    "state::boundary_layer_moisture::decrease",
    "state::precipitation::decrease"
  ],
  "scores": {
    "path_applicability_min": 0.78,
    "cross_edge_context_coherence_min": 0.82,
    "mean_claim_relevance": 0.84,
    "length_factor": 0.86,
    "path_rank": 0.46
  }
}
```

Again: `path_rank` is a ranking score only.

---

# 43. Stage 17 — final synthesis evidence package

The final generative model should receive only:

```text
original user question
parsed QuerySpec
compact Query Context Facets
selected paths
selected contradictory/alternative Claims
selected exact SourceBlocks
query-area derived Facets needed for spatial translation
explicit scoring metadata needed for limitations
```

Do not include all candidate Contexts or the entire graph.

Respect:

```text
evidence_input_budget_tokens = 16000
hard_llm_input_budget_tokens = 20000
```

If too large:

1. reduce SourceBlocks per Claim;
2. reduce lower-ranked paths;
3. remove duplicate evidence passages;
4. never increase reasoning level to compensate for oversized input.

---

# 44. Final synthesis reasoning policy

Default:

```text
qwen3.6:27b
thinking = low
```

Use `medium` only when the selected evidence contains substantial:

```text
contradictory findings
multiple context-dependent mechanism paths
spatial/directional transfer reasoning
trade-offs among interventions
```

Use a single final synthesis call; do not add an LLM reranker.

The evidence package must remain inside the hard input budget even with medium reasoning.

---

# 45. Final synthesis should return structured answer JSON

Do not let the model invent citation formatting directly.

## Prompt: `final_synthesis.txt`

```text
SYSTEM

Answer the user's land-atmosphere question using ONLY the supplied Query
Context, selected graph Claims, and SourceBlocks.

Every substantive scientific statement must cite the supporting Claim IDs.
Every query-area environmental/spatial fact used in the answer must cite
its Query Facet IDs.

Treat each supplied Claim relationship and description as the complete
scientific content. The synthesis request receives only SourceBlock IDs,
pages, sections, and block types for provenance; full selected passages remain
in `query_report.json` but are not shown to the synthesis model. Check every clause in an
answer item against its listed Claims. Preserve exact comparisons, ranges,
and qualifiers; evidence for one stated forcing change does not support every
increase in that forcing.

You may combine supported Claims into a mechanism chain only when that path
is explicitly supplied.

Do not invent mechanisms, intermediate steps, locations, magnitudes,
directions, or distances.

Distinguish:
- direct literature-supported findings;
- transfer/inference from literature to the query area;
- query-area derived environmental facts;
- uncertainty, mismatch, missing information, and contradictory evidence.

Context/applicability scores are retrieval scores, not probabilities of truth.
Do not call them confidence.

For spatial advice, translate terms such as upwind/downwind into the user's
geography only if the supplied query spatial Facets establish the direction.

Return schema-valid JSON only.

USER QUESTION
{question}

QUERY SPEC
{query_spec}

QUERY CONTEXT
{query_context}

SELECTED PATHS AND CLAIMS
{selected_paths}

CONTRADICTORY / ALTERNATIVE EVIDENCE
{contradictions}

SOURCE BLOCKS
{source_blocks}
```

Output:

```json
{
  "direct_answer": [
    {
      "text": "...",
      "support_claim_ids": ["P0042_CL09"],
      "support_query_facet_ids": ["Q0001_F03"],
      "kind": "transfer_inference"
    }
  ],
  "mechanisms": [],
  "spatial_guidance": [],
  "conditions_and_limitations": [],
  "contradictory_evidence": []
}
```

---

# 46. Deterministic grounding validation

After final synthesis JSON:

1. verify every `support_claim_id` exists in selected evidence;
2. verify every `support_query_facet_id` exists;
3. reject/repair unsupported IDs;
4. attach Paper metadata and exact SourceBlock IDs deterministically;
5. render citations/references in the final UI/text;
6. log any answer item with no scientific support IDs.

If a scientific statement has no valid support, remove it or mark it explicitly as unsupported rather than silently emitting it.

---

# 47. Reference rendering

For each answer item:

```text
Claim ID
  ↓
Paper ID
  ↓
Paper title / DOI / year
  ↓
SourceBlock IDs + page/section locator
```

The final user answer can render compact references such as:

```text
... supported in a Sahel wet-season study [1].
```

with reference metadata:

```text
[1] Paper title, year — Claims CL09, CL11 — SourceBlocks ...
```

The underlying JSON preserves exact IDs even if the visible answer uses compact citations.

---

# 48. Derived-data references

If the answer says:

```text
"The wet-season upwind side of your watershed is southwest."
```

that is not a paper claim. It must trace to a Query Facet produced from the configured wind dataset and method.

Keep separate provenance classes:

```text
literature evidence
query-area derived evidence
user-provided fact
```

---

# 49. What to show the user about similarity

Do not force raw scores into every answer.

Recommended UI layers:

```text
main answer → concise scientific result
"Why these studies?" → Context/applicability summary
"Details / JSON" → full context_matches / claim_matches / paths
```

When scores are shown, label them clearly:

```text
Context match score
Spatial-configuration match
Intervention similarity
Path applicability rank
```

Never:

```text
Scientific confidence = 82%
```

---

# 50. Tunable parameters

The most important query-time parameters are:

```text
context ANN top-k
Context rerank top-k
Facet notion/content α
domain weights
missing-coverage penalty λ_missing
Context minimum threshold τ_q (later)
Claim conditioning weight β
conditioning mismatch threshold (later)
State mapping top-k / ambiguity margin
Transition top-k
Claim semantic top-k
candidate Claim top-k
max path length
beam width
max paths
cross-edge Context threshold τ_c (later)
path length penalty
spatial directional-persistence threshold
spatial transfer threshold (later)
SourceBlocks per Claim
paths/Claims supplied to final synthesis
final evidence token budget
Qwen thinking level
```

Store all values in `query_report.json` for reproducibility.

---

# 51. Parameter policy

Separate parameters into:

## Scientific/retrieval parameters

```text
α
domain weights
λ_missing
β
τ_q
τ_c
max path length
spatial transfer conditions
```

Evaluate these against scientific benchmark queries.

## Engineering parameters

```text
ANN top-k
beam width
batch size
cache size
embedding dimension
token budgets
```

Tune these mainly for recall/latency/memory after scientific correctness is acceptable.

---

# 52. No hard thresholds initially

Embedding-score thresholds are not intrinsically calibrated.

Recommended MVP:

```text
use top-k retrieval
log distributions
manually label matches/non-matches
calibrate thresholds from benchmark data
```

Only then set:

```text
min_context_score
min_known_conditioning_score
cross_edge_context_threshold
spatial_transfer_min_score
```

This avoids arbitrary scientific-looking cutoffs.

---

# 53. Query types for benchmark

Benchmark at least these families:

```text
Forward:      What happens if X is changed here?
Backward:     What could produce Y here?
A→B:          Could X produce Y here, and how?
Comparison:   Which of X1/X2 is more relevant for Y here?
Transfer:     Does evidence from elsewhere apply here?
Spatial:      Where should X occur relative to wind/terrain/edges?
Scale:        How large / how far / local vs remote?
Global:       What does literature report without one target area?
```

Comparison queries can execute two ordinary A→B/backward runs and compare the resulting ranked evidence; no new graph schema is required.

---

# 54. Query benchmark metrics

Evaluate separately:

```text
query parsing accuracy
source State mapping accuracy
target State mapping accuracy
Query Facet faithfulness
enrichment correctness
coarse Context recall@K
Facet match precision
Context rerank nDCG/recall
missing-vs-mismatch classification
conditioning-Facet match accuracy
Claim applicability precision/recall
relevant contradiction recall
path endpoint correctness
path Context coherence
unsupported path-step rate
spatial direction correctness
spatial scale-transfer correctness
citation/SourceBlock correctness
unsupported final assertion rate
answer usefulness by expert review
```

---

# 55. Retrieval ablations

Run explicit versions:

```text
V0 whole-Context cosine only
V1 domain-wise Facet MaxSim
V2 MaxSim + Claim conditioning Facets
V3 MaxSim + Context-gated graph search
V4 UOT reranking
V5 context-coherent path search
```

Keep each extra layer only if it improves benchmark performance.

---

# 56. UOT later

Unbalanced Optimal Transport can later replace or rerank MaxSim because it naturally allows unmatched Facets.

Do not make UOT an MVP dependency.

The report schema should remain compatible:

```text
facet alignments
matched mass
unmatched query mass
unmatched candidate mass
domain score
overall score
```

---

# 57. Query failure/warning states

Do not silently return a polished answer when retrieval is weak.

Possible warnings:

```text
NO_SPATIAL_SUPPORT
QUERY_CONTEXT_SPARSE
NO_RELIABLE_WIND_DIRECTION
STATE_MAPPING_AMBIGUOUS
LOW_CONTEXT_COVERAGE
NO_APPLICABLE_CLAIMS
NO_PATH_FOUND
CROSS_CONTEXT_PATH_REJECTED
SPATIAL_SCALE_MISMATCH
CONTRADICTORY_EVIDENCE
SOURCEBLOCK_BUDGET_TRUNCATED
FINAL_GROUNDING_VALIDATION_FAILED
```

Warnings belong in query JSON and may be summarized in the answer when relevant.

---

# 58. Caching

Cache deterministic/reusable work:

```text
query-area enrichment by geometry + date/season configuration
Query Facet embeddings
State mapping results for repeated endpoint phrases
candidate Context effective Facet sets
indexed Context-to-Context coherence scores
SourceBlock loads
```

Do not cache final answers across materially different Query Contexts.

---

# 59. Query execution pseudocode

```python
def answer_query(user_question, spatial_input=None):
    # 1. One small LLM parse call.
    parsed = parse_query_qwen(
        user_question,
        model="qwen3.6:27b",
        thinking="no",
    )

    query = build_minimal_query_spec(parsed)
    query.mode = determine_mode(parsed)

    # 2. Resolve location and create sparse Context.
    spatial_support = resolve_spatial_support(parsed, spatial_input)
    query_context = build_sparse_query_context(parsed, spatial_support)

    # 3. Deterministic enrichment.
    if enrichment_is_possible(spatial_support):
        derived_facets = enrich_query_area(spatial_support, parsed)
        query_context.facets.extend(derived_facets)

    # 4. Deterministic/embedding State mapping.
    source_candidates = map_state(query.source)
    target_candidates = map_state(query.target)

    # 5. Embeddings.
    embed_query_facets(query_context)
    embed_query_context(query_context)
    embed_intervention_if_present(query)

    if query.mode == "global":
        context_matches = []
    else:
        # 6. Coarse ANN then exact Facet-set reranking.
        contexts = context_ann(query_context, top_k=CFG.context_ann_top_k)
        context_matches = [
            score_context_maxsim(query_context, c, CFG)
            for c in contexts
        ]
        context_matches = rank_contexts(context_matches)

    # 7. Candidate Claim union.
    claims = collect_candidate_claims(
        context_matches=context_matches,
        source_candidates=source_candidates,
        target_candidates=target_candidates,
        intervention=query.intervention_description,
        question=user_question,
    )

    # 8. Applicability including optional conditioning Facets.
    claim_reports = [
        score_claim_applicability(query_context, query, cl, context_matches)
        for cl in claims
    ]

    # 9. Query-specific subgraph and graph search.
    subgraph = build_query_subgraph(claim_reports, CFG)
    paths = search_paths(
        subgraph,
        mode=query.mode,
        source_candidates=source_candidates,
        target_candidates=target_candidates,
        cfg=CFG,
    )

    paths = score_context_coherence(paths, CFG)
    paths = rank_paths(paths, CFG)

    # 10. Seek contradictory/alternative evidence deliberately.
    contradictions = retrieve_relevant_contradictions(paths, query_context, CFG)

    # 11. Gather exact evidence.
    source_blocks = select_source_blocks(paths, contradictions, CFG)

    # 12. Build reproducible report before synthesis.
    report = build_query_report(
        query=query,
        query_context=query_context,
        state_mapping={"source": source_candidates, "target": target_candidates},
        context_matches=context_matches,
        claim_matches=claim_reports,
        paths=paths,
        contradictions=contradictions,
        source_blocks=source_blocks,
        config=CFG,
    )

    # 13. One final LLM call.
    thinking = choose_final_thinking_level(report)  # low or medium
    answer_json = synthesize_grounded_answer_qwen(
        report,
        thinking=thinking,
        hard_input_budget=CFG.hard_llm_input_budget_tokens,
    )

    # 14. Deterministic grounding/citation validation.
    validated = validate_answer_support(answer_json, report)
    rendered = render_answer_with_references(validated, report)

    report["answer"] = validated
    save_query_report(report)

    return rendered, report
```

---

# 60. Recommended MVP order

## MVP 1

```text
query parse
explicit Query Context
State mapping
Context ANN
Facet MaxSim
Context-gated Claims
forward/backward/A→B path search
SourceBlock grounding
structured final synthesis
query_report.json
```

## MVP 2

```text
query-area enrichment symmetry
missing-vs-mismatch coverage scoring
Claim CONDITIONED_BY Facet scoring
contradiction retrieval
```

## MVP 3

```text
spatial/directional enrichment
upwind/downwind polygon sectors
patch/edge/scale handling
spatial transfer reporting
```

## MVP 4

```text
cross-edge Context coherence
benchmark-calibrated thresholds
comparison queries
```

## MVP 5

```text
UOT experiments
more advanced Context clustering / regime stratification
```

---

# 61. Normative exact algorithms for query execution

This section is **normative** and resolves every shorthand such as “resolve”, “retrieve”, “score”, “select”, “boost”, “seek contradictions”, “coherent”, and “adequate” used earlier in this document.

The query implementation must not ask Qwen to invent retrieval logic. Qwen is used only for query parsing and final grounded synthesis.

---

## 61.1 Query parsing validation and repair

After `query_parse.txt` returns JSON:

1. schema-validate;
2. reject any environmental Facet whose text is not entailed by the user's question;
3. reject coordinates/geometry not literally supplied by the user;
4. normalize endpoint whitespace/punctuation only;
5. preserve parser `ambiguities` but do not ask a second semantic clarification call by default.

The entailment check in step 2 is deterministic string/source-span validation: the parser must additionally return `supporting_text_span` for every explicit Facet and endpoint. The span must be an exact substring of the user question after Unicode normalization. If absent, that parsed item is discarded.

Update the parser schema accordingly:

```json
{
  "concept": "forest cover",
  "state": "decrease",
  "supporting_text_span": "reduce forest cover"
}
```

This prevents the parsing model from smuggling pretrained environmental knowledge into Query Context.

---

## 61.2 SpatialSupport resolution precedence

Use this exact precedence:

```text
1. explicit polygon/GeoJSON supplied by caller
2. explicit lat/lon supplied by caller
3. registered watershed/planning-area ID
4. saved application object ID
5. named-place gazetteer resolution
6. unresolved/null
```

Named-place resolution may auto-resolve only when exactly one gazetteer candidate satisfies all explicit administrative/country qualifiers. Otherwise keep `geometry=null` and warning `SPATIAL_REFERENCE_AMBIGUOUS`.

The generative model never geocodes.

For a non-global named query place without caller-supplied geometry, copy the user's complete place phrase into `enrichable_study_location_name`. A unique qualified gazetteer match becomes approximate Point geometry. Query artifacts must retain the extracted name, resolved geometry, approximate resolution, and cached resolver decision.

---

## 61.3 Query enrichment is the same code as indexing enrichment

Do not implement a separate query enrichment stack.

Call the exact functions defined in indexing Section 96.15 using the query geometry and query temporal window. The output fields and algorithm versions must be identical so query and indexed Contexts share the same descriptive language.

Temporal-window selection precedence:

```text
explicit user season/date
> intervention season explicitly parsed from question
> application-provided planning season
> configured climatological annual/seasonal defaults
```

If no season is specified, emit separate seasonal wind Facets only when their regimes materially differ; otherwise emit the annual regime. “Materially differ” is deterministic: pairwise seasonal mean wind-from directions differ by `>=45°` **or** directional-persistence values differ by `>=0.25` **or** mean speeds differ by a factor `>=1.5`.

---

## 61.4 Upwind/downwind sector algorithm

Use projected metric coordinates appropriate for the geometry centroid. If no local CRS is configured, use an automatically selected UTM zone when geometry spans `< 6°` longitude; otherwise use a local azimuthal-equidistant projection centered on the target centroid.

For a reliable mean flow vector `v_to`:

1. compute polygon centroid `mu` in projected coordinates;
2. for every analysis pixel centroid `x`, compute `r = dot(x-mu, unit(v_to))`;
3. compute `q = spatial.sector_quantile` (default `0.33`);
4. within target polygon:
   - `r <= quantile(r,q)` → upwind sector;
   - `r >= quantile(r,1-q)` → downwind sector;
   - remainder → crosswind/interior.
5. for an external buffer, classify pixels using `r` relative to the target polygon projection interval:
   - `r < min_target_r` → external upwind;
   - `r > max_target_r` → external downwind;
   - otherwise lateral/crosswind.

Do not issue one directional sector when wind directional persistence `< directional_persistence_threshold`.

---

## 61.5 Windward/leeward terrain algorithm

Only compute this when a DEM and reliable wind vector exist.

1. Sample DEM along transects parallel to the wind-to vector through the target/intervention area.
2. A barrier exists when elevation rises by at least configured `terrain_barrier_relief_m` within configured `terrain_barrier_search_km` upwind of the target and then falls by at least the same threshold downwind.
3. The slope facing incoming flow is windward; the opposite descending side is leeward.
4. If fewer than `terrain_barrier_min_fraction` of transects satisfy the barrier condition, do not create windward/leeward Facets.

Initial configuration:

```yaml
spatial:
  terrain_barrier_relief_m: 300
  terrain_barrier_search_km: 50
  terrain_barrier_min_fraction: 0.5
```

These thresholds are engineering definitions for detecting a barrier, not universal atmospheric laws; benchmark before using for planning guidance.

---

## 61.6 State endpoint mapping

Use the same canonical concept and state-direction registries as indexing.

For each query endpoint:

### Step A — exact alias

If normalized concept hits `state_aliases.yaml`, create one candidate with:

```text
concept_similarity = 1.0
mapping_method = exact_alias
```

### Step B — embedding candidates

Otherwise embed the normalized concept and retrieve `state_mapping.top_k` canonical **concepts** by cosine.

Clamp negative cosine to zero.

### Step C — state compatibility

Normalize query state using the curated state-direction registry.

For each canonical State under the retrieved concept:

```text
state_compatible = True  if normalized state exactly matches
state_compatible = True  if query state is empty/unspecified
state_compatible = False otherwise
```

Discard incompatible States. Do not infer that one directional state is “close enough” to another.

### Step D — candidate ranking

```text
mapping_score = concept_similarity
```

Sort descending, then stable `state_id`.

If exact alias exists, use it as the sole seed unless multiple canonical States share the same concept and the query state is unspecified.

Otherwise use the top `seed_top_k` compatible candidates. Mark `STATE_MAPPING_AMBIGUOUS` when top1-top2 margin `< candidate_margin`.

Do not use an uncalibrated absolute cosine threshold in MVP.

---

## 61.7 Query embedding texts

Use these exact strings:

```text
Facet notion:  "{domain} | {notion}"
Facet content: "Domain: {domain}\nNotion: {notion}\nDescription: {description}"
```

Whole Context text:

1. reconstruct query Facets;
2. sort by configured domain order, then notion, then ID;
3. concatenate each as the Facet content text separated by `\n---\n`;
4. prepend SpatialSupport only as `Spatial kind: ...; name: ...` and never raw coordinates.

Intervention text:

```text
"Intervention: {intervention_description}"
```

Claim-retrieval text:

```text
"Question: {user_question}\nSource: {source concept | state or NONE}\nTarget: {target concept | state or NONE}"
```

All vectors are L2-normalized.

---

## 61.8 Coarse Context ANN and rerank set

For non-global queries with at least one Query Facet:

1. query Context vector index for `ann_top_k`;
2. deduplicate Context IDs;
3. compute exact domain-wise MaxSim for every returned Context;
4. sort by `S_context`, tie by `S_semantic`, then ANN cosine, then Context ID;
5. retain first `rerank_top_k` for downstream Claim-scope retrieval, but write all ANN candidates and scores to the audit report.

If the Query Context has **zero Facets**, skip Context ANN entirely and set `context_gate_disabled_reason="empty_query_context"`.

---

## 61.9 Facet MaxSim details

For each query Facet `q` in domain `d`, compute pair score against every effective candidate Facet in `d`. Select the maximum; ties within `1e-6` are broken by higher content cosine, then candidate Facet ID.

Domain score is the arithmetic mean over query Facets in that domain; candidate extra Facets do not add score or penalty.

Semantic score:

```python
known = [(w_d, S_d) for d in query_domains if candidate_has_domain(d)]
S_semantic = sum(w*s for w,s in known) / sum(w for w,s in known)
```

If `known` is empty, set `S_semantic=0`, `coverage=0`, `S_context=0`.

Coverage uses weights of **query domains**, exactly as defined earlier. Missing candidate domains are never assigned similarity zero inside `S_semantic`; their effect enters only through coverage.

---

## 61.10 Claim conditioning score

For each indexed conditioning Facet, run the same Facet pair score against query Facets in the same domain.

Known conditioning coverage:

```text
known_count / total_conditioning_facets
```

`S_conditioning` is the arithmetic mean of known best matches. Unknown query domains do not become zero matches.

Claim context applicability:

- Context-scoped Claim: `S_context(scope Context)`.
- Transition-scoped Claim: `S_context(FROM Context)` because the user's current environment is the baseline to which an intervention is applied.
- If context gating is disabled because Query Context is empty, `A_claim_context = null` rather than `1.0`.

Combined applicability:

```python
if A_claim_context is None:
    A_claim = None
elif S_conditioning is None:
    A_claim = A_claim_context
else:
    A_claim = (1-beta)*A_claim_context + beta*S_conditioning
```

Never replace unknown applicability with a fabricated neutral score.

---

## 61.11 Transition/intervention similarity

If `intervention_description` exists:

```text
S_transition = max(0, cosine(query_intervention_embedding,
                             transition.transition_embedding))
```

For Context-scoped Claims or queries without an intervention description, `S_transition=null`.

Do not fold FROM/TO Context embeddings into this score; environmental applicability is already handled separately.

---

## 61.12 Candidate Claim union

Generate five channels exactly:

### Channel A — Context scope

For every retained reranked Context, collect:

- Claims scoped directly to that Context;
- Claims scoped to Transitions whose FROM Context is that Context.

### Channel B — source endpoint

For each source State seed, collect outgoing Claims. If more than 100 per seed, order by Claim embedding cosine to the query Claim-retrieval vector and keep 100.

### Channel C — target endpoint

For each target State seed, collect incoming Claims. Same 100-per-seed cap.

### Channel D — semantic Claim ANN

Take `claim_semantic_top_k` by Claim embedding cosine.

### Channel E — Transition ANN

If intervention exists, take `transition_top_k` Transitions by transition cosine and collect their Claims.

Union by `claim_id`. Preserve channel membership in the report.

Compute all ranking components for every union member, then retain `candidate_claim_top_k` by the exact Claim ranking formula below.

---

## 61.13 Endpoint relevance

Let `M_source(claim)` be the maximum mapping score among source seed States that exactly equal the Claim FROM State ID; if none, `0`.

Let `M_target(claim)` analogously use the Claim TO State ID.

Then:

```text
forward:  S_endpoint = M_source
backward: S_endpoint = M_target
a_to_b:   S_endpoint = (M_source + M_target) / 2
global:   use the same rule implied by whichever endpoints are supplied;
          if neither endpoint supplied -> null
```

This score does not use semantic similarity between arbitrary State IDs; that semantic work already happened during endpoint mapping.

---

## 61.14 Claim semantic relevance

```text
S_claim_semantic = max(0, cosine(query_claim_retrieval_embedding,
                                 claim.claim_embedding))
```

This is relevance of the Claim text to the question, not applicability.

---

## 61.15 Exact Claim ranking formula

Add to configuration:

```yaml
claim_ranking:
  weights:
    context: 0.45
    mechanism: 0.20
    intervention: 0.15
    endpoint: 0.20
```

For each Claim, form only components that are non-null. Renormalize their configured weights to sum to 1.

```text
R_claim = weighted_mean(
    A_claim,
    S_claim_semantic,
    S_transition,
    S_endpoint
)
```

If Context is available, `A_claim` is always included and remains the largest default weight.

Sort Claims by `R_claim`, then `A_claim` (null last), then `S_endpoint`, then Claim ID.

No hard applicability threshold is used until benchmark calibration.

---

## 61.16 Query-specific subgraph construction

Create adjacency maps in memory:

```python
outgoing[state_id] -> list[claim_id]
incoming[state_id] -> list[claim_id]
```

Only retained candidate Claims are present. Each Claim object carries `R_claim`, `A_claim`, scope, and Context report references.

Claims with invalid/missing endpoints are excluded and logged.

---

## 61.17 Coherence Context for a Claim

To compare adjacent Claims, define one deterministic Context representation per Claim.

- Context-scoped Claim → Effective(scope Context).
- Transition-scoped Claim → **background Context**, defined as the effective Facets inherited by both FROM and TO Contexts from their common ancestors. If no common ancestor exists, use Effective(FROM Context).

This avoids treating the intervention-specific target land state itself as the environmental regime used for cross-paper coherence.

Cache the resulting background Context embedding/Facet set by Transition ID.

---

## 61.18 Cross-edge Context coherence

For adjacent Claims `i,j`:

1. obtain their coherence Contexts from Section 61.17;
2. compute directional MaxSim both ways using all domains present in the temporary “query” Context;
3. compute `S_sym = 0.5*(S_ij + S_ji)`;
4. cache by ordered pair of Context IDs/signatures.

For a path, `C_path=min(S_sym adjacent pairs)`; single-Claim path gets `1.0`.

If either coherence Context has zero Facets, adjacent coherence is `null`. Such a path is not rejected in MVP, but is ranked with `coherence_known=false` and receives no coherence multiplier; see Section 61.20.

---

## 61.19 Cycle and path expansion rules

A path state sequence may not revisit a State ID. A Claim ID may not repeat. This removes ordinary cycles.

For forward/backward search, terminal States may be any State not yet visited. For A→B, a path is complete only when it reaches one target seed State.

Maximum length is counted in Claims.

Do not traverse an associative Claim backward as if it implied causality; backward mode is reverse **retrieval traversal**, and the final answer must preserve each Claim's original relation type.

---

## 61.20 Partial and final path scoring

For a partial/full path:

```text
A_path = min(non-null A_claim values) or null if all null
C_path = min(known adjacent coherence values) or null if none known
M_path = mean(R_claim values)
length_factor = 1 / (1 + path_length_penalty*(L-1))
```

Ranking multiplier:

```text
A_factor = A_path if non-null else 1.0
C_factor = C_path if non-null else 1.0
R_path = A_factor * C_factor * M_path * length_factor
```

Missing Context/coherence therefore does not masquerade as a low match, but `context_unknown=true` / `coherence_unknown=true` must be reported and may lower user-facing transferability language.

Beam-search partial score is exactly the same formula on the partial path.

At each depth, sort partial paths by `R_path`, then shorter length, then lexicographic Claim-ID tuple, and keep `beam_width`.

Collect completed paths throughout search; after search, sort by the same final score and retain `max_paths`.

---

## 61.21 Contradiction and alternative-evidence retrieval

Run this after leading paths are selected.

For every focal Claim on the top `synthesis.top_paths` paths:

1. identify canonical FROM concept and TO concept (ignore state);
2. retrieve all Claims with the same FROM concept and same TO concept;
3. classify outcome relation deterministically using the curated state-polarity registry:
   - opposite polarity (`increase` vs `decrease`) → `opposite`;
   - `no_detectable_change` vs non-null → `null_alternative`;
   - same outcome state but different relation/mechanism description → `supporting_alternative`;
   - unrecognized state relation → `alternative`, not contradiction.
4. exclude the focal Claim itself;
5. compute Context applicability and Claim ranking to the query using the same functions as ordinary candidates;
6. retain up to 3 items per focal Claim, prioritizing `opposite`, then `null_alternative`, then other alternatives, each sorted by query applicability/relevance.

Deduplicate across focal Claims by Claim ID.

This procedure deliberately searches the graph; it does not rely on the final LLM to notice contradictions.

---

## 61.22 Spatial relevance score

Only compute when the user asks a spatial/directional question or Query Context contains `spatial_configuration` Facets.

For a Claim:

1. `S_spatial_context` = `spatial_configuration` domain score of its supporting Context, if available;
2. `S_spatial_conditioning` = mean known matches among conditioning Facets in `spatial_configuration`, if any;
3. `S_spatial_text` = cosine between an embedding of the spatial part of the user question and an embedding of Claim description + Transition description, clamped to zero.

Combine present values with equal weights:

```text
S_spatial = mean(present spatial components)
```

Do not change the scientific Context score. Use `S_spatial` only as a tie-break/secondary ranking field for spatial queries and report it separately.

---

## 61.23 Numeric scale extraction and scale compatibility

**Normative refinement:** Section 63.4 overrides the scalar-equivalent shortcuts below when geometry type is known.

Run a deterministic regex/unit parser over `spatial_configuration` Facet descriptions and Claim descriptions to extract explicit length/area ranges such as `10–40 km`, `50 km`, `250 x 250 km`, `km²`.

Store these as query-time auxiliary hints, never as new graph schema fields.

If both query and study provide comparable **length** scales, compute:

```text
if ranges overlap: S_scale = 1.0
else:
    ratio = max(mid_q, mid_c) / min(mid_q, mid_c)
    S_scale = exp(-abs(log(ratio)) / log(4))
```

For area, convert to equivalent length `sqrt(area)` before comparison.

If either side lacks an explicit comparable scale, `S_scale=null` and the answer must not claim exact scale transfer.

A planning recommendation with a numeric distance/patch size may be emitted only when that number appears in selected literature evidence or is a deterministic measurement of the user's own geometry. Never interpolate a new scientific optimum.

---

## 61.24 Translating a spatial relation to local geography

**Normative refinement:** apply the relation-family-specific rules in Section 63.1–63.3. The generic gate below applies only to `local_advection` unless Section 63 specifies another method.

A directional local recommendation requires all of:

```text
1. selected literature evidence explicitly supports the relation
2. Query wind/vector Facet is derived with persistence >= threshold
3. relevant spatial_configuration Context score exists
4. no selected contradictory evidence with comparable/higher applicability reverses the relation
5. scale compatibility is not known to be poor
```

If satisfied, translate only the relation, e.g. `upwind` → the computed local sector label. Geographic cardinal direction is generated from the deterministic vector/sector calculation, not by Qwen.

If any condition fails, final synthesis receives `spatial_translation_allowed=false` and may discuss the literature relation without naming a local side.

---

## 61.25 SourceBlock selection

A Claim already contains exact supporting SourceBlock IDs. Evidence selection therefore ranks only among **its own cited blocks**; it never searches the whole paper for replacement support.

For each cited block `b`:

```text
S_direct = cosine(embed(claim.description), block_embedding_b)
S_query  = cosine(query_claim_retrieval_embedding, block_embedding_b)
section_bonus = 0.05 if section is Results/Analysis else 0.02 if Discussion else 0
block_score = 0.7*max(0,S_direct) + 0.3*max(0,S_query) + section_bonus
```

If block embeddings are unavailable, use deterministic priority:

```text
Results/Analysis > Discussion > Conclusion > Methods > other
```

Take up to `max_source_blocks_per_claim`, always including at least one block if the Claim has valid evidence.

When a transfer condition is essential, also include the top evidence block for each conditioning Facet actually used in `S_conditioning`, capped at one block per conditioning Facet.

No evidence block outside a Claim/Facet's indexed provenance may be presented as direct support for that object.

---

## 61.26 Evidence-package budget trimming

Build the final synthesis package in this order:

1. QuerySpec + compact Query Context (mandatory);
2. top paths in descending `R_path`;
3. for each newly added Claim, add at least one selected SourceBlock;
4. add second SourceBlocks only after every retained Claim has one;
5. add contradictions/alternatives in their ranked order;
6. add conditioning-Facet evidence needed for transfer explanations.

If token budget is exceeded:

- first remove second/extra SourceBlocks;
- then remove lowest-ranked contradiction/alternative items;
- then remove lowest-ranked paths as whole units;
- never keep a Claim in the synthesis package without at least one valid supporting SourceBlock.

If even the highest-ranked complete path plus mandatory context exceeds the hard budget, truncate to the highest-ranked Claim(s) that fit and add warning `SOURCEBLOCK_BUDGET_TRUNCATED`.

---

## 61.27 Final reasoning-level selection

Use deterministic policy:

```python
complex_evidence = (
    len(contradictions) > 0
    or len(selected_paths) >= 4
    or any(p.get("spatial_translation_allowed") for p in selected_paths)
    or count_distinct_supported_outcome_states(selected_claims) >= 2
)
thinking = "medium" if complex_evidence else "low"
```

Never use `high` thinking. Never use `medium` merely because the prompt is long.

---

## 61.28 Final grounding validation

Do not “repair” unsupported scientific text with a second generative call.

For every answer item:

1. all `support_claim_ids` must be in the supplied synthesis package;
2. all `support_query_facet_ids` must be in Query Context;
3. if `kind` is scientific (`direct_finding`, `transfer_inference`, `mechanism`, `spatial_guidance`), require at least one valid Claim ID;
4. `spatial_guidance` that names a local sector/direction additionally requires at least one valid Query Facet ID and `spatial_translation_allowed=true`;
5. attach exact Paper and SourceBlock provenance deterministically.

If an item fails, drop the item and log `UNSUPPORTED_SYNTHESIS_ITEM`.

If all direct-answer items are dropped, return a deterministic fallback message stating that retrieved evidence could not support a grounded answer and set `FINAL_GROUNDING_VALIDATION_FAILED`.

---

## 61.29 Context/Claim threshold calibration

When labeled benchmark data exist, calibrate each threshold separately rather than choosing round numbers.

For a candidate threshold metric:

1. split labeled benchmark queries by paper/intervention family into development/test sets so near-duplicate papers do not leak across;
2. on development set, sweep all unique observed score values;
3. choose the lowest threshold that achieves precision target `>=0.80` while maximizing recall; if no threshold meets precision target, leave threshold disabled;
4. report recall, precision, F1, and coverage on held-out test set;
5. version the chosen threshold with benchmark version/date.

For cross-edge coherence, optimize **path coherence precision** rather than Context-match precision.

Do not tune thresholds on final-answer wording scores.

---

## 61.30 Default configuration additions

Add these missing parameters to `query_pipeline.yaml`:

```yaml
claim_ranking:
  weights:
    context: 0.45
    mechanism: 0.20
    intervention: 0.15
    endpoint: 0.20

spatial:
  directional_persistence_threshold: 0.55
  spatial_transfer_min_score: null
  sector_quantile: 0.33
  terrain_barrier_relief_m: 300
  terrain_barrier_search_km: 50
  terrain_barrier_min_fraction: 0.5

contradictions:
  per_focal_claim_top_k: 3

evidence_selection:
  direct_weight: 0.7
  query_weight: 0.3
  results_section_bonus: 0.05
  discussion_section_bonus: 0.02
```

Every effective value, including defaults, is copied into `query_report.json`.

---

## 61.31 Exact query-report reproducibility fields

In addition to the existing report fields, store:

```text
query_pipeline_version
prompt versions
Qwen model identifier
embedding model identifier + dimension
State alias registry version
state-direction registry version
enrichment dataset/version + geometry hash
effective parameter values
candidate IDs per retrieval channel
all tie-break decisions
warnings/failure states
```

This makes the similarity JSON an auditable retrieval artifact rather than a display-only object.

---

## 61.32 Query implementation acceptance test

A query run is conformant when, for fixed graph snapshot/config/model versions:

- parser output passes exact source-span validation;
- candidate Context/Claim sets are reproducible;
- all component scores can be recomputed from stored IDs/vectors/config;
- every returned path consists only of context-gated candidate Claims;
- every scientific answer item maps to Claim → Paper → SourceBlock;
- every local spatial direction maps to a deterministic Query Facet/geometry calculation;
- missing information is represented as null/unknown, never silently converted to zero or certainty.

# 63. Corpus-derived query rules and stress tests

This section records changes found necessary by testing the query design against the supplied papers. It is normative where it tightens Sections 35–37 and 61.22–61.24.

## 63.1 Spatial relation is not one problem

Do not treat every occurrence of `upwind/downwind` as transferable by the same local wind-sector algorithm.

At query time derive a **report-only auxiliary set** `spatial_relation_families` from selected Claim/Facet evidence. This is not a graph-schema field.

Allowed families:

```text
local_advection
patch_gradient_edge
distance_decay
orographic_windward_leeward
moisture_recycling_source_sink
remote_teleconnection
non_directional_spatial
unknown
```

High-precision deterministic classification uses normalized Claim description + relevant `spatial_configuration` Facet text:

```text
local_advection:
  propagate downwind, downstream propagation, background wind carries,
  advected downwind, upstream/downstream patch

patch_gradient_edge:
  patch, edge, boundary, gradient, heterogeneity, mosaic,
  dry patch, wet patch, patch size

distance_decay:
  distance-decay, annulus/annuli, halo, within <distance>,
  non-local effect at <distance>

orographic_windward_leeward:
  windward, leeward, ridge, mountain barrier, rain shadow

moisture_recycling_source_sink:
  precipitationshed, moisture recycling, evaporation source,
  precipitation sink, source region, sink region,
  terrestrial evaporation contribution

remote_teleconnection:
  teleconnection, remote circulation response, distant region,
  intercontinental, remote land-use impact
```

An evidence item may have multiple families. If no high-precision rule fires, use `unknown`; do not force an embedding-based label in the MVP.

Store the matched phrases and SourceBlock IDs in `query_report.json`.

## 63.2 Spatial translation method by family

The local placement algorithm is selected by relation family:

```text
local_advection
    → Sections 61.4 + 61.24 may translate upwind/downwind to local sectors.

orographic_windward_leeward
    → Section 61.5 may translate to local windward/leeward terrain only.

patch_gradient_edge
    → may transfer relative layout/edge/patch guidance;
      cardinal direction requires local_advection evidence as well.

distance_decay
    → may transfer only a literature-supported distance/range statement;
      never infer a preferred direction.

moisture_recycling_source_sink
    → DO NOT use simple mean-wind sectors as a substitute for a precipitationshed.
      Local placement requires a dedicated moisture-tracking/source-contribution
      layer for the Query area. Without it, discuss the generic upwind/source
      dependency and set `spatial_translation_allowed=false` for placement.

remote_teleconnection
    → never map the relation to a local cardinal sector from climatological wind.
      Requires a dedicated dynamical/teleconnection analysis outside the MVP.

unknown
    → no local spatial translation.
```

This distinction is required by the paper corpus: Froidevaux-type storm propagation is a local advective mechanism, whereas Keys-style precipitationsheds are probabilistic moisture-source regions whose boundaries vary with threshold and integration period.

## 63.3 Revised spatial-translation gate

Replace the generic gate in Section 61.24 with:

```python
family = spatial_relation_families(selected_evidence)

if "local_advection" in family:
    allowed = (
        literature_supports_relative_direction
        and query_wind_persistence >= threshold
        and spatial_context_is_known
        and not comparable_contradiction_reverses_relation
        and scale_not_known_poor
    )
    method = "wind_sector"

elif "orographic_windward_leeward" in family:
    allowed = (
        literature_supports_windward_leeward_relation
        and terrain_barrier_detected
        and query_wind_persistence >= threshold
        and not comparable_contradiction_reverses_relation
    )
    method = "terrain_windward_leeward"

elif "moisture_recycling_source_sink" in family:
    allowed = query_has_moisture_source_map
    method = "moisture_source_map" if allowed else null

else:
    allowed = False
    method = null
```

`patch_gradient_edge` and `distance_decay` can still produce non-cardinal spatial guidance even when `allowed=false` for directional translation.

Report:

```json
{
  "spatial_translation": {
    "families": ["local_advection", "patch_gradient_edge"],
    "allowed": true,
    "method": "wind_sector",
    "matched_evidence": ["..."],
    "blocking_reasons": []
  }
}
```

## 63.4 Spatial scale parser correction

Section 61.23 must preserve geometry type rather than converting every number to one equivalent length.

Parse into auxiliary records:

```json
{
  "kind": "range | radius | distance_band | rectangle | area | dimensionless_ratio",
  "value": null,
  "min": 10,
  "max": 40,
  "x": null,
  "y": null,
  "unit": "km",
  "source_text": "10–40 km"
}
```

Rules:

1. `1–2 km`, `2–4 km`, etc. in annulus/halo language → `distance_band`;
2. `100 × 300 km` → `rectangle`, preserving both axes;
3. `4 < λ/z_i < 9` → `dimensionless_ratio`; never convert to kilometres without a query-side boundary-layer height;
4. area may be converted to `sqrt(area)` **only for coarse candidate ranking** and must remain labeled `area_equivalent_length=true`;
5. compare like geometry types whenever possible;
6. if a study's effect is explicitly anisotropic/oriented, do not reduce it to a scalar equivalent length for planning guidance.

This is required by the Cohn annulus, Rabin landscape-size, and Patton/Rieck heterogeneity-scale cases.

## 63.5 Outcome-specific spatial footprint

A spatial relation belongs to a Claim/result, not automatically to the entire paper or intervention.

Example from the African Great Lakes study: precipitation influence can be concentrated over the lake surface while near-surface temperature has a pronounced downwind footprint. Therefore:

- compute spatial relevance from the **Claim's** description/conditioning Facets first;
- use Context-level spatial Facets only as background;
- never propagate a spatial footprint discovered for one outcome to sibling Claims.

In the report, each Claim gets its own:

```text
spatial_relation_families
parsed_scales
spatial_translation eligibility
```

## 63.6 Query similarity JSON must separate four ideas

For each candidate Claim/Context, report separately:

```text
semantic_similarity      # how similar known conditions are
coverage                 # how much of query context could be compared
conditioning_match       # match to Facets specifically relevant to Claim
spatial_transfer         # relation-family-specific transfer information
```

Do not combine these into one user-facing number.

`R_claim` / `R_path` may combine components for ranking, but the report must retain the raw components and the final answer must not describe the combined score as scientific confidence.

## 63.7 Unknown-vs-mismatch ranking tie-break

When two candidates have similar `R_claim` or `R_path`, prefer the one with more known applicability rather than allowing unknown context to look equally strong.

Do **not** change unknown similarity to zero. Add a deterministic tie-break tuple:

```text
Claim sort:
  R_claim desc,
  applicability_known desc,
  context_coverage desc,
  A_claim desc (null last),
  endpoint relevance desc,
  Claim ID

Path sort:
  R_path desc,
  all_claim_context_known desc,
  mean_context_coverage desc,
  coherence_known desc,
  shorter length,
  Claim-ID tuple
```

A score difference `<= 0.02` is considered a tie for the first three tie-break fields. This value is an engineering ranking margin and must be benchmarked.

## 63.8 Corpus query stress tests

The following should become query regression tests.

### Q1 — irrigation and heat

```text
Could expanding irrigation reduce extreme daytime heat in this South Asian agricultural area?
```

Expected behavior:

- Thiery irrigation/hot-extreme Claims rank highly when Query Context resembles South Asian irrigation-hotspot conditions;
- answer distinguishes hot extremes from annual-mean temperature;
- cites direct Thiery evidence;
- cited introduction claims about remote rainfall do not appear as Thiery results.

### Q2 — afforestation and clouds

```text
Would afforestation increase low-level cloud cover here?
```

Expected behavior:

- Duveiller ranks highly;
- answer is conditional/observational, not universal causal certainty;
- forest type, geographic/seasonal context can appear when matched/known;
- missing snow/season information is reported as unknown, not mismatch.

### Q3 — where to place a wet/vegetated patch for convection

```text
If I can restore one large patch, should it be upwind or downwind to favor convective rainfall?
```

Expected behavior:

- Froidevaux/Taylor/Rabin-type spatial evidence is retrieved;
- local wind vector may translate relative `upwind/downwind` into local sectors only when persistence is adequate;
- answer notes that convection may initiate over dry/warm areas and strengthen after propagation over wetter areas when the relevant wind regime matches;
- no generic “plant everything upwind” rule is emitted.

### Q4 — protect remote forest to sustain rainfall

```text
Which land outside this watershed should be protected to sustain our rainfall?
```

Expected behavior:

- Keys precipitationshed/moisture-recycling literature is relevant;
- simple climatological mean-wind sector is **not** used as the answer;
- if no query-side moisture-source map exists, system explains the mechanism but abstains from naming exact external polygons;
- with a moisture-source map, source-contribution geometry can be reported and cited as derived data plus literature mechanism evidence.

### Q5 — distance of deforestation warming

```text
Could forest clearing outside the project site still increase maximum temperature here, and how far away has this been observed?
```

Expected behavior:

- Cohn ranks highly;
- annuli 1–2, 2–4, 4–10, 10–50 km are preserved as study design/evidence;
- no effect beyond the studied range is invented;
- distance guidance does not invent a direction.

### Q6 — patch size

```text
Is a larger land-cover patch always more effective at triggering convection?
```

Expected behavior:

- Rieck/Patton-type evidence is retrieved;
- system rejects a monotonic “larger is always better” synthesis;
- reports scale-specific/non-monotonic evidence and context dependence.

### Q7 — atmospheric state reversal

```text
Do wetter/greener patches always make convective clouds more likely?
```

Expected behavior:

- Rabin/Froidevaux/Guillod/Klein-type evidence provides competing signs/locations;
- contradictions/alternatives retrieval is activated;
- answer stratifies by atmospheric moisture/stability, wind, spatial vs temporal relationship, and time of day where supported;
- no universal sign is returned.

### Q8 — solar farm local heat

```text
Could a large PV installation warm the surrounding air here?
```

Expected behavior:

- Barron-Gafford ranks for semiarid-like Contexts;
- nighttime 3–4 °C study result is cited as study-specific evidence, not transferred as an exact local prediction;
- final answer distinguishes evidence from transfer inference.

## 63.9 Query regression-test harness

Maintain `benchmark/queries.yaml` with:

```yaml
- id: Q4_precipitationshed
  query: "Which land outside this watershed should be protected to sustain our rainfall?"
  expected:
    must_retrieve_paper_family: [precipitationshed, moisture_recycling]
    forbidden_translation_method: [wind_sector]
    must_set_warning_if_no_moisture_map: true
```

For each benchmark query, store assertions over machine-readable `query_report.json`, not exact final prose:

```text
candidate paper/Claim presence
minimum/maximum rank bands
required spatial relation family
forbidden translation method
required warning/abstention
required provenance chain
contradiction/alternative presence when applicable
```

The final-answer text can vary; the retrieval and grounding behavior must satisfy the assertions.

## 63.10 Implementation readiness criterion

The pipeline is implementation-ready only when:

1. Sections 96 and 61 are implemented literally or versioned replacements are documented;
2. the corpus indexing invariants in Section 97.7 pass on the supplied papers;
3. query regression tests in Section 63.8 pass at the report/grounding level;
4. thresholds remain disabled or are benchmark-calibrated where specified;
5. no coding agent is required to invent a merge, scoring, spatial-transfer, evidence-selection, or abstention rule.

Passing these tests is more important than reproducing an exact number of Contexts/Facets/Claims.


# 64. Final architectural summary

```text
USER QUESTION
    │
    ▼
Qwen3.6 query parse                    [thinking=no]
    │
    ▼
minimal QuerySpec
    +
Sparse Query Context
    │
    ├── explicit user Facets
    └── deterministic environmental/spatial enrichment
    │
    ▼
Qwen3 embeddings
    │
    ├── State mapping
    ├── coarse Context ANN
    ├── Transition retrieval
    └── Claim retrieval
    │
    ▼
domain-wise Facet MaxSim
    + coverage accounting
    + conditioning-Facet matching
    │
    ▼
context-gated Claims
    │
    ▼
query-specific subgraph
    │
    ▼
forward / backward / A→B / global traversal
    │
    ▼
context-coherent path ranking
    + contradiction search
    + spatial transfer checks
    │
    ▼
exact SourceBlocks
    │
    ▼
compact evidence package
    │
    ▼
Qwen3.6 grounded synthesis             [thinking=low; medium if complex]
    │
    ▼
structured answer JSON
    │
    ▼
deterministic support validation + citation rendering
    │
    ├── user-facing referenced answer
    └── reportable query_report.json with all similarity scores
```

The central rule is:

> **Use semantic methods to estimate environmental applicability; use graph structure and provenance deterministically; use the LLM only to parse the user's language and synthesize already-selected evidence.**
