# Land–Atmosphere Knowledge Graph / GraphRAG — Project Summary

## 1. Main goal

Build a **context-conditioned scientific reasoning system** for land–atmosphere interactions using hundreds of research papers.

The system should support questions such as:

- What land-use / land-cover (LULC) change could increase rainfall in this watershed?
- How could dust storms be reduced here?
- What might happen if a given amount of deforestation occurs?
- How could intervention **A** affect outcome **B**?
- What does the literature say globally when no specific location is supplied?

The objective is **not** just paper retrieval.  
It is to retrieve and connect literature-supported **mechanism chains**, while conditioning their applicability on the environmental context of the query area.

---

# 2. Core scientific idea

Land–atmosphere responses are strongly context dependent.

The same LULC change can produce different outcomes depending on:

- background hydroclimate / aridity
- season
- soil moisture
- atmospheric stability
- wind regime / advection
- patch size and configuration
- upwind/downwind position
- terrain and elevation
- land-cover state
- spatial scale
- etc.

Therefore the system should **not** represent a study as one embedding or a list of scalar variables.

Instead:

> A study is represented as a hierarchy of **Contexts**, each composed of rich semantic **Facets**.

The graph then stores literature-supported relationships between scientific states.

---

# 3. Minimal scientific schema

The final minimal schema is:

```text
Paper
Context
Facet
Transition
Claim
State
```

Plus one technical provenance object:

```text
SourceBlock
```

No separate ContextGraph / EvidenceGraph / MechanismGraph is required.  
These are simply different views over the same property graph.

---

# 4. Context

A `Context` is the environmental / experimental / scenario state under which findings are valid.

Example:

```text
C1 = Brazil / wet-season common context
│
├── C1.1 = intact forest control
├── C1.2 = 20% deforestation
└── C1.3 = 50% deforestation
```

Children inherit their parent context.

So:

```text
Effective(C1.1)
=
Facets(C1)
+
Facets(C1.1)
```

The child stores only what is different.

This prevents repetition.

---

# 5. Facet

A `Facet` is one coherent description of part of the context.

Schema:

```json
{
  "domain": "atmosphere",
  "notion": "background wind regime",
  "description": "During JJAS the low-level flow is predominantly southwesterly, generally 4–8 m/s, moisture-bearing and directionally persistent.",
  "origin": "reported"
}
```

## Allowed broad domains

```text
spatial_configuration
land_surface
hydrology
atmosphere
climate
substrate_terrain
other
```

The `notion` is open vocabulary. There is no separate `Facet.scope`; season, layer, time-of-day, spatial scale, and similar qualifiers stay naturally in `description`, or become a distinct child `Context` when they define a genuinely different study state. As an extraction-consistency guideline, `notion` is usually a concise 2–8 word noun phrase and `description` is usually 20–60 words, with no padding or omission merely to meet the range.

Examples:

```text
background wind regime
seasonal moisture-bearing circulation
landscape heterogeneity
forest configuration
soil-moisture regime
terrain setting
climate regime
upwind land-cover composition
```

The schema does **not** require predefined columns such as:

```text
wind_speed
wind_direction
soil_type
aridity_index
patch_area
```

Numbers, ranges, directions, units and categories can remain inside the rich description.

---

# 6. Why this representation was chosen

Many climate/environmental variables cannot be reduced cleanly to one number.

Example:

```text
"During the monsoon, winds are predominantly SW,
moisture-bearing, moderate, and directionally persistent.
Pre-monsoon winds are weaker and more variable."
```

This is scientifically useful as a whole.

Therefore:

> Numeric normalization is optional augmentation, not the foundation of similarity.

---

# 7. Spatial support

Location is special because it may be used for optional environmental enrichment.

A Context may contain:

```json
{
  "kind": "point | patch | watershed | region | climate_zone | global | unresolved",
  "name": "...",
  "geometry": null,
  "resolution": "exact | approximate | named_region | global | unresolved"
}
```

Important rules:

- Do not invent coordinates.
- Do not convert a broad region such as “Amazon basin” to one arbitrary centroid.
- A Context with no precise location remains valid.

---

# 8. Transition

A `Transition` represents the land-use / scenario comparison being studied.

Example:

```text
T1:
C1.1 forest control
      ↓
C1.2 pasture scenario
```

Schema:

```json
{
  "from_context_id": "C1.1",
  "to_context_id": "C1.2",
  "description": "Approximately 30% of forest was replaced by pasture."
}
```

A Transition may represent:

- actual intervention
- model perturbation
- scenario comparison
- observational comparison

---

Field-writing ranges are soft consistency targets: Context labels are usually 3–12 words; Transition labels 2–10 words; Transition descriptions 10–50 words. Paper-local aliases should remain actual names/IDs rather than invented semantic synonyms. No field is padded to meet a range. Evidence lists use the smallest sufficient set of directly supporting SourceBlocks rather than every block shown to the extractor; derived Facets retain dataset/product + version/method provenance separately from their semantic description.

# 9. Claim

A `Claim` is one evidence-backed relationship reported by a paper.

Example:

```text
evapotranspiration decrease
        ↓
atmospheric moisture supply decrease
```

Schema:

```json
{
  "scope_id": "T1",
  "from": {
    "concept": "evapotranspiration",
    "state": "decrease"
  },
  "to": {
    "concept": "atmospheric moisture supply",
    "state": "decrease"
  },
  "relation": "causal",
  "description": "Reduced evapotranspiration lowered atmospheric moisture supply.",
  "conditioning_facet_ids": ["F12", "F18"]
}
```

`conditioning_facet_ids` is optional. It points to ordinary Context Facets that the paper specifically indicates are material to interpreting or transferring the Claim; it should not simply list every Context Facet. Claim endpoint concepts are kept compact (usually 1–8 words), endpoint states compact (usually 1–5 words), and Claim descriptions usually 15–50 words while preserving material magnitude, seasonal, spatial, threshold, or conditional qualifiers. These are soft writing targets, never hard validators.

Only two relation types are needed initially:

```text
causal
associative
```

Do not create a huge relation ontology initially.

---

# 10. State

Claims connect shared canonical `State` nodes.

Examples:

```text
evapotranspiration :: decrease
precipitation :: decrease
forest cover :: decrease
boundary-layer moisture :: decrease
```

Graphically:

```text
State
  ↓
Claim
  ↓
State
```

The Claim remains a node so that each relationship retains:

- paper
- context
- experiment
- evidence
- description
- causal/associative status

Multiple papers may support the same mechanism without being collapsed into one universal “truth edge”.

---

# 11. Important graph rule

Do **not** store:

```text
ET ↓ ──CAUSES──► Rainfall ↓
```

as the primary source-of-truth edge.

Instead:

```text
ET ↓
  ↑ FROM
Claim CL17
  ↓ TO
Rainfall ↓
```

The Claim is the evidence-bearing relationship.

---

# 12. Provenance

Every extracted object should point back to exact source text.

Use stable `SourceBlock` IDs such as:

```text
P017:S02:P0014
P017:S04:P0037
P017:FIG3_CAPTION
```

Important principle:

> Deduplicate knowledge, not evidence.

If the same finding appears in Results, Discussion and Conclusion, store one Claim with multiple evidence block IDs.

---

# 13. Stable blocks

Stable blocks are generated for **every paper**, even short ones.

They are used for:

- evidence provenance
- debugging
- targeted extraction
- re-extraction
- long-paper evidence retrieval

They are **not** the semantic study units.

The paper/context remains the semantic unit.

---

# 14. Chunking decision

Naive fixed-size “chunk → extract independently → merge” was rejected.

Instead:

> Map the paper first, then assemble evidence around known scientific objects.

Routing:

```text
if useful paper text <= ~15k tokens:
    use whole paper for paper mapping
else:
    use section scouts
    then consolidate into one paper map
```

The ~15k threshold is configurable.

---

# 15. Paper mapping

Paper mapping is the first structural LLM step.

Its task is only to identify:

- Contexts
- parent/child hierarchy
- aliases
- spatial support
- Transitions
- blocks relevant to later Facet extraction
- blocks relevant to later Claim extraction

Example result:

```text
C1 = Brazil common context

C1.1 = forest control
aliases: CTRL, control simulation

C1.2 = deforestation scenario
aliases: EXP1, DEF20

T1 = C1.1 → C1.2
```

Paper mapping does **not** extract detailed mechanism chains.

---

# 16. Long papers

For long papers:

```text
section
  ↓
section scout
```

A scout only identifies:

- scenario names
- aliases
- locations
- likely transitions
- important source blocks
- cross-references

Then all scout outputs are consolidated into one global paper map.

The scouts are routing hints, not final scientific evidence.

---

# 17. Evidence bundles

After the paper map exists, evidence is assembled around each scientific object.

## Context bundle

For a Context, retrieve raw blocks relating to:

```text
study area
location
climate
season
wind
atmosphere
LULC
soil
terrain
hydrology
configuration
management
```

Use:

- seed blocks from paper mapping
- exact alias matching
- lexical search
- Qwen embeddings
- ±1 neighbouring paragraph

Then send the assembled raw evidence bundle to the Facet extractor.

## Transition / Claim bundle

For each Transition, gather:

- experiment definition
- Results
- Discussion
- figure/table captions
- mechanism passages
- outcome passages

Then run Claim extraction.

---

# 18. LLM usage during indexing

Primary extraction model:

```text
qwen3.6:27b via Ollama
```

Use structured JSON-schema outputs.

Logical stages:

```text
1. Paper mapping

2A. Context Facet extraction
2B. Claim extraction

3. Per-paper consolidation
```

For long papers there may additionally be:

```text
section scouts
map consolidation
optional context reconciliation
```

Typical simple paper:

```text
~4–7 LLM calls
```

Complex papers require more calls because they contain more actual scientific objects.

---

# 19. What the LLM does

LLM is used for:

```text
discovering Context structure
extracting rich Facets
extracting evidence-backed Claims
resolving ambiguous paper-local context structure
deduplicating/consolidating paper-level extraction
```

---

# 20. What the LLM must NOT do

Do not use the LLM for:

```text
geocoding
Earth Engine queries
raster extraction
aridity calculations
wind climatology calculation
unit normalization as a requirement
MaxSim
UOT
graph traversal
path ranking
scientific confidence scoring
Neo4j writes
```

Also:

- no invented mechanisms
- no invented coordinates
- no LLM confidence probability
- no automatic reconciliation of reported vs derived context

---

# 21. Claim extraction rule

Never invent intermediate mechanisms.

If the paper says:

```text
deforestation → rainfall decrease
```

extract only that.

Do not expand automatically to:

```text
deforestation
→ ET decrease
→ PBL moisture decrease
→ cloud decrease
→ rainfall decrease
```

unless each link is supported by the paper.

---

# 22. Consolidation

After extraction, a final paper-level consolidation call may:

- merge duplicate Contexts
- merge duplicate Facets
- merge duplicate Claims with identical scope/meaning
- repair IDs
- preserve all provenance
- preserve contradictions
- finalize hierarchy

It may **not**:

- invent new facts
- invent mechanisms
- merge different response metrics
- remove contradictory Claims
- assign confidence
- infer missing information

---

# 23. Optional context enrichment

After extraction, some Contexts may be enriched algorithmically.

Possible sources:

```text
geocoding
Earth Engine
ERA5 / ERA5-Land
DEM
Köppen raster
aridity datasets
soil datasets
LULC rasters
```

Initial enrichment families:

```text
climate regime
hydroclimatic / aridity regime
seasonal wind regime
terrain setting
land-surface / spatial configuration
```

Derived information is stored as **additional Facets** with:

```text
origin = "derived"
```

Reported Facets remain untouched.

---

# 24. Enrichment symmetry

The same enrichment pipeline should later run on the user's query area.

This creates a shared environmental language between:

```text
paper Contexts
and
new watershed/query Context
```

This is important for context similarity.

---

# 25. Embeddings

Use:

```text
Qwen3-Embedding
```

For every Facet create two embeddings.

## Notion embedding

```text
domain | notion
```

Example:

```text
atmosphere | background wind regime
```

## Content embedding

```text
Domain: atmosphere
Notion: background wind regime
Description: ...
```

Also create:

```text
Context.retrieval_embedding
Claim.claim_embedding
Transition.transition_embedding
State.concept_embedding
```

---

# 26. Whole-Context embedding

Each effective Context gets one coarse embedding used only for initial candidate retrieval.

Example constructed text:

```text
Context: Amazon wet-season forest control

[climate]
...

[atmosphere]
...

[hydrology]
...

[land_surface]
...

[substrate_terrain]
...
```

This is not the final similarity metric.

---

# 27. Context similarity

The main similarity method should compare **sets of Facets**, not one vector.

Start with domain-wise MaxSim.

For each domain:

```text
query facets
      ↕
candidate facets
```

For each query Facet, take its best candidate match.

Conceptually:

\[
S_d(Q,C)
=
\frac{1}{|Q_d|}
\sum_{q \in Q_d}
\max_{c \in C_d} s(q,c)
\]

Then combine domains:

\[
S(Q,C)
=
\frac{\sum_d w_d S_d}{\sum_d w_d}
\]

This prevents one enriched domain containing many correlated Facets from dominating similarity.

---

# 28. Facet pair similarity

For Facets `q` and `c`:

\[
s(q,c)
=
\alpha \cos(E_{notion}(q),E_{notion}(c))
+
(1-\alpha)\cos(E_{content}(q),E_{content}(c))
\]

`α` controls type/notion vs descriptive-content similarity.

---

# 29. UOT

Unbalanced Optimal Transport is a later experimental reranker.

It is attractive because it can align two sets of context information while allowing unmatched Facets.

Example:

```text
query has soil moisture
candidate paper does not
```

The system should not force soil moisture to match terrain simply because every element must be aligned.

Recommended progression:

```text
V0 whole-context cosine
V1 Facet MaxSim
V2 MaxSim + context gating
V3 UOT
V4 context-coherent path search
```

Only keep additional complexity if benchmarks show improvement.

---

# 30. Context-aware graph reasoning

The central scientific rule is:

> A mechanism path is not transferable merely because every edge exists somewhere in the literature.

Bad path example:

```text
forest loss → ET decrease       Amazon
ET decrease → PBL change        Great Plains
PBL change → convection         Sahel
convection → rainfall           generic LES
```

The path may look plausible but mix incompatible contexts.

Therefore graph search must be **query-conditioned**.

---

# 31. Query-specific subgraph

Correct order:

```text
query Context
    ↓
retrieve applicable evidence Claims
    ↓
context gate
    ↓
construct query-specific subgraph
    ↓
search mechanism paths
```

Not:

```text
find any graph path
    ↓
check context afterward
```

---

# 32. Path applicability

For each evidence Claim edge:

\[
A_e(Q)=S(Q,C_e)
\]

where `C_e` is the effective evidence context.

Initial conservative path score:

\[
A_\pi = \min_{e \in \pi} A_e(Q)
\]

So a path is limited by its weakest context-transfer step.

Later, path-context coherence can also compare the supporting contexts of adjacent edges.

---

# 33. No scientific confidence score

Do not produce:

```text
confidence = 0.87
```

from an LLM.

Instead retain observable metadata such as:

```text
number of supporting papers
number of independent contexts
evidence types
contradictory Claims
context match
```

Any single score is a **retrieval/ranking score**, not a probability that the mechanism is true.

---

# 34. Query classes

Only four are needed:

## Forward

```text
A → ?
```

Example:

```text
What happens if 20% of forest is removed?
```

## Backward

```text
? → B
```

Example:

```text
What interventions might increase rainfall?
```

## A → B

Example:

```text
How could irrigation affect precipitation?
```

## Global

Example:

```text
How does deforestation affect rainfall across the literature?
```

Backward is simply reverse graph traversal.

---

# 35. Online query architecture

Target online flow:

```text
user question
    ↓
LLM parse query
    ↓
temporary query Context + A/B target
    ↓
optional query-area enrichment
    ↓
Qwen embeddings
    ↓
coarse Context ANN retrieval
    ↓
Facet MaxSim / UOT reranking
    ↓
context-gated Claims
    ↓
forward / backward / A→B search
    ↓
top context-coherent mechanism paths
    ↓
retrieve SourceBlocks
    ↓
one final LLM synthesis
```

Only about **two generative LLM calls per user query**:

1. query parsing
2. final answer synthesis

Graph traversal and scoring should be deterministic Python/Neo4j operations.

---

# 36. Storage architecture

Recommended:

```text
Filesystem / object store
    +
Neo4j
    +
Python
```

## Filesystem/object store

Stores:

```text
original PDF
Nemotron parser output
clean Markdown
SourceBlocks
candidate extraction JSON
consolidated JSON
enrichment artifacts
GeoJSON
final_paper.json
pipeline manifests
```

This is the reproducible source/archive.

## Neo4j

Stores active searchable graph:

```text
Paper
Context
Facet
Transition
Claim
State
SourceBlock
```

plus vector/full-text indexes.

## Python

Performs:

```text
pipeline orchestration
validation
MaxSim
UOT
context inheritance
context gating
path search
enrichment
graph ingestion
```

---

# 37. Neo4j graph structure

```text
(Paper)-[:HAS_CONTEXT]->(Context)

(Context)-[:PARENT_OF]->(Context)

(Context)-[:HAS_FACET]->(Facet)

(Paper)-[:HAS_TRANSITION]->(Transition)
(Transition)-[:FROM]->(Context)
(Transition)-[:TO]->(Context)

(Paper)-[:HAS_CLAIM]->(Claim)

(Claim)-[:SCOPED_TO]->(Context)
or
(Claim)-[:SCOPED_TO]->(Transition)

(Claim)-[:FROM]->(State)
(Claim)-[:TO]->(State)
(Claim)-[:CONDITIONED_BY]->(Facet)

(Facet)-[:SUPPORTED_BY]->(SourceBlock)
(Context)-[:SUPPORTED_BY]->(SourceBlock)
(Transition)-[:SUPPORTED_BY]->(SourceBlock)
(Claim)-[:SUPPORTED_BY]->(SourceBlock)

(SourceBlock)-[:IN_PAPER]->(Paper)
```

---

# 38. Why Neo4j is sufficient initially

For hundreds of papers, one graph database plus its vector indexes should be enough.

Do not prematurely add:

```text
Neo4j
Postgres
Qdrant
Elasticsearch
RDF store
```

all at once.

Add another datastore only when a concrete scaling or geospatial requirement appears.

---

# 39. Canonicalization

Contexts are **never globally merged**.

Example:

```text
Amazon forest Context from Paper A
Amazon forest Context from Paper B
```

remain separate evidence contexts.

Shared mechanism `State` concepts may be canonicalized conservatively.

Initial policy:

```text
exact/manual alias → merge
embedding similarity → candidate only
ambiguous → leave separate
```

---

# 40. Graph re-indexing

Do not make the graph the extraction workspace.

Flow:

```text
LLM output
    ↓
candidate JSON
    ↓
validation
    ↓
consolidation
    ↓
final_paper.json
    ↓
Neo4j
```

If extraction improves later:

```text
PDF
 ↓
new extraction
 ↓
new final_paper.json
 ↓
replace that paper's subgraph transactionally
```

Historical versions remain on disk.

---

# 41. PDF indexing pipeline

Final indexing sequence:

```text
PDF
 ↓
NVIDIA Nemotron-Parse v1.2
 ↓
raw parse
 ↓
deterministic Markdown cleaning
 ↓
stable SourceBlocks
 ↓
paper-size routing
 ↓
paper mapping
 ↓
Context Registry
 ↓
Context evidence bundles
 ↓
Facet extraction
 ↓
Transition/Claim evidence bundles
 ↓
Claim extraction
 ↓
optional context reconciliation
 ↓
paper consolidation
 ↓
validation
 ↓
optional spatial/environmental enrichment
 ↓
State canonicalization
 ↓
Qwen3 embeddings
 ↓
final_paper.json
 ↓
transactional Neo4j graph ingestion
 ↓
full-text + vector indexes
```

---

# 42. Parser and Markdown

Primary parser:

```text
NVIDIA Nemotron-Parse v1.2
```

Keep:

```text
text
page number
reading order
headings
tables
figure captions
table captions
equations
```

Markdown cleaning must be deterministic:

```text
Unicode normalization
header/footer removal
conservative hyphen repair
whitespace normalization
preserve paragraphs
preserve tables
preserve captions
mark bibliography
```

Never delete the raw parser output.

---

# 43. final_paper.json

This is the deterministic interchange format consumed by the graph builder.

Top-level:

```json
{
  "paper": {},
  "source_blocks": [],
  "contexts": [],
  "facets": [],
  "transitions": [],
  "claims": [],
  "states": [],
  "evidence_links": [],
  "unresolved_conflicts": [],
  "metadata": {}
}
```

The graph builder must contain no LLM logic.

---

# 44. Important boundary cases

The design explicitly supports:

```text
multiple study areas in one paper
many scenarios under one location
wet/dry seasonal contexts
theoretical studies
global model studies
review papers
observational comparisons
null results
contradictory findings
different response metrics
different temporal aggregation
local vs non-local effects
missing location
broad region names
numbers embedded in prose
wind roses
table-only findings
figure-caption findings
cross references such as "EXP2"
```

---

# 45. Failure principle

Never silently convert failure into an empty extraction.

Stages should explicitly return states such as:

```text
OK
SKIPPED_NOT_APPLICABLE
NEEDS_REVIEW
FAILED_PARSE
FAILED_SCHEMA
FAILED_REFERENCE_VALIDATION
FAILED_GRAPH_INGEST
```

---

# 46. Main configurable scientific parameters

For retrieval:

```text
α = notion/content similarity balance

domain weights w_d

missing-information handling

context applicability threshold τ_q

optional cross-edge context threshold τ_c

maximum path length

path length penalty

candidate Context top-k

candidate Claim top-k
```

Engineering parameters:

```text
ANN top-k
beam width
batch size
embedding dimension
cache size
```

Scientific and engineering parameters should be evaluated separately.

---

# 47. Evaluation plan

Before scaling to hundreds of papers, manually annotate 20–50 diverse papers.

Extraction metrics:

```text
Context discovery recall
Context over/under splitting
hierarchy accuracy
Transition accuracy
Facet precision/recall
Claim precision/recall
causal vs associative accuracy
scope accuracy
evidence grounding accuracy
```

Retrieval experiments:

```text
whole-context cosine
vs
Facet MaxSim
vs
MaxSim + context gating
vs
UOT
vs
context-coherent path search
```

Critical ablation:

```text
context-aware graph search
vs
context-blind graph search
```

---

# 48. Central design philosophy

The project can be summarized as:

> **LLM for semantic extraction.  
> Embeddings for semantic matching.  
> Python/Neo4j for deterministic graph computation.  
> External datasets for optional context enrichment.**

And the central scientific idea is:

> **Mechanism paths are useful only to the extent that the contexts supporting them are transferable to the query context.**

---

# 49. Detailed implementation specifications

Two implementation-ready specifications are maintained:

```text
land_atmosphere_kg_indexing_pipeline.md
land_atmosphere_kg_query_pipeline.md
```

The indexing specification includes a normative implementation-resolution section defining exact block retrieval/bundling, semantic consolidation, enrichment, State canonicalization, retries, and graph-ingest behavior.

The query specification includes a normative execution section defining exact State mapping, Context/Facet similarity, Claim ranking, path scoring/coherence, contradiction retrieval, spatial translation, SourceBlock selection, grounding validation, and threshold calibration.

The coding rule is: **deterministic Python/Neo4j owns every operation that can be specified algorithmically; Qwen3.6:27b is used only for bounded semantic extraction/classification and final synthesis, with no/low/medium thinking only.**

This summary is intended as the compact project-level reference for continuing the conversation without carrying the entire detailed specifications.


## Implementation-resolution and corpus-test status (2026-08-19)

The indexing/query specifications now include normative exact algorithms for ambiguous operations and corpus-derived regression tests. Key additions are: exact Context-vs-Facet split rules for conditional/reversing findings; optional Claim→conditioning-Facet adjudication; own-result vs cited-background filtering; typed spatial-scale parsing; relation-family-aware spatial transfer (`local_advection`, `patch_gradient_edge`, `distance_decay`, `orographic_windward_leeward`, `moisture_recycling_source_sink`, `remote_teleconnection`); and machine-readable query-report acceptance tests. A paper-level specification stress test passed the documented static invariants. A live Qwen3.6:27b corpus benchmark is still required after implementation before tuning hard thresholds.
