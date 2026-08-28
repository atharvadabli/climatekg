# Land–Atmosphere Knowledge Graph: Problem Statement and Project Overview

## 1. Problem Statement

Scientific studies on land-use and land-cover change often report that interventions such as deforestation, afforestation, irrigation, wetland restoration, cropland expansion, paddy cultivation, or solar-farm development can alter local and regional climate.

The difficulty is that these effects are **strongly context dependent**. The same intervention may produce different, weaker, stronger, or even opposite responses depending on factors such as:

- hydroclimate and season;
- soil-moisture regime;
- atmospheric stability and background circulation;
- land-cover type and baseline state;
- patch size, heterogeneity, and spatial arrangement;
- upwind/downwind or windward/leeward position;
- terrain and elevation;
- local versus remote moisture transport;
- spatial and temporal scale of the study.

A conventional literature search can find papers mentioning a land intervention and an outcome, but it does not reliably answer the more important question:

> **Does the mechanism reported in this study apply to this particular place, intervention, and environmental setting?**

The project therefore aims to build a context-aware scientific Knowledge Graph and query system that can retrieve, connect, and explain literature-supported mechanisms while preserving the environmental conditions under which those mechanisms were observed or simulated.

---

## 2. Intended Users and Questions

The system is intended for users such as farmers, local land-use planners, climate-adaptation scientists, engineers, and researchers.

Typical questions include:

- What happens if forest cover is reduced here?
- Could irrigation reduce hot extremes in this watershed?
- Would afforestation increase cloud cover or rainfall here?
- What land-management intervention could reduce local heat?
- Where should restoration be placed relative to prevailing winds?
- Could an upwind land-cover change alter rainfall in this area?
- Does a mechanism reported in the Sahel, Amazon, or another region transfer to this location?
- Through what sequence of mechanisms could intervention **A** lead to outcome **B**?

The system should support forward, backward, source-to-target, comparison, and transferability queries.

---

## 3. Core Design Idea

The central design principle is to separate **scientific graph structure** from **environmental applicability**.

Graph structure is explicit and symbolic:

- `Paper`
- `Context`
- `Facet`
- `Transition`
- `Claim`
- `State`
- `SourceBlock`

Environmental applicability is represented mainly through **rich descriptive Facets**, rather than a large rigid table of variables.

A Facet contains:

- `domain` — broad controlled category such as atmosphere, hydrology, land surface, climate, terrain, or spatial configuration;
- `notion` — short open-vocabulary scientific idea;
- `description` — rich evidence-grounded description of the actual condition;
- `origin` — reported, derived, or other provenance category;
- evidence/provenance references.

For example, instead of separately encoding wind speed, wind direction, humidity, season, and persistence, one atmospheric Facet may describe a coherent seasonal moisture-bearing circulation regime.

This preserves scientific meaning while still allowing semantic comparison through embeddings.

---

## 4. Claims and Mechanisms

A `Claim` represents one evidence-supported relationship, for example:

`evapotranspiration | decrease  →  atmospheric moisture supply | decrease`

Each Claim is scoped to a Context or Transition and linked to exact supporting SourceBlocks.

Claims may also reference the subset of Context Facets that materially condition their interpretation or transferability.

Canonical `State` nodes provide graph connectivity, while Claim descriptions preserve important qualifiers such as magnitude, seasonality, spatial extent, directionality, or conditionality.

The system must never invent unsupported intermediate mechanisms simply to create a complete path.

---

## 5. Indexing Pipeline

The indexing pipeline converts scientific PDFs into a provenance-preserving graph:

`PDF → parse → clean markdown → SourceBlocks → paper map → Contexts / Facets / Transitions / Claims → consolidation → State canonicalization → embeddings → Neo4j`

The preferred parser is NVIDIA Nemotron-Parse v1.2. Semantic extraction uses `qwen3.6:27b` through Ollama with controlled no/low/medium reasoning budgets so that prompts remain within the model context window.

Deterministic algorithms are used wherever possible. The LLM is used only for genuinely semantic judgments such as Context identification, Facet extraction, Claim extraction, or limited reconciliation.

Every extracted scientific object must remain traceable to the smallest sufficient supporting SourceBlocks.

---

## 6. Query Pipeline

The query pipeline constructs a temporary query Context using the same representation as indexed paper Contexts.

Query information may come from:

1. explicit user statements;
2. location or watershed geometry;
3. trusted environmental enrichment such as climate, atmospheric, hydrological, terrain, land-cover, or spatial-configuration datasets.

The system must not hallucinate environmental conditions from pretrained model knowledge.

The main query flow is:

`user question → query parse → query Context → optional environmental enrichment → Context retrieval → Facet-level similarity → Claim applicability filtering → context-coherent graph search → SourceBlock retrieval → cited final synthesis`

Context similarity is primarily semantic and set-based. Whole-context embeddings may provide coarse retrieval, but final applicability uses Facet matching, domain balancing, coverage handling, and later optionally unbalanced optimal transport.

Missing information must be distinguished from a true environmental mismatch.

---

## 7. Spatial and Directional Reasoning

Spatial configuration is a first-class part of the system because many land–atmosphere mechanisms depend on **where** an intervention occurs.

The system should preserve and reason about evidence involving:

- patch size and heterogeneity;
- edge and gradient effects;
- upwind/downwind relations;
- windward/leeward relations;
- local advection;
- distance decay;
- moisture recycling and precipitationsheds;
- remote teleconnections.

These mechanisms must not be collapsed into one generic spatial rule. For example, a local mean-wind upwind/downwind translation is not equivalent to a remote moisture-recycling pathway.

When giving location-specific guidance, the literature provides the transferable mechanism, while local environmental data determine what directions or areas correspond to terms such as *upwind*, *downwind*, *windward*, or *leeward* in the target region.

---

## 8. Grounding and Transparency

Every substantive answer should be auditable through:

`answer statement → mechanism path → Claim(s) → Context / conditioning Facets → Paper → SourceBlock(s)`

The query system should also generate a machine-readable report containing items such as:

- overall Context similarity;
- domain-level similarity;
- matched and unmatched Facets;
- Claim applicability scores;
- conditioning-Facet matches;
- path ranking values;
- supporting SourceBlocks;
- missing information and contradictions.

These numbers are **retrieval and applicability scores**, not probabilities that a scientific claim is true.

---

## 9. Non-Goals

The system is not intended to:

- create a universal causal climate model;
- replace numerical weather or climate simulation;
- invent mechanisms absent from the literature;
- assign pseudo-probabilistic scientific confidence scores;
- force all environmental knowledge into a rigid ontology;
- assume that a mechanism transfers merely because its graph endpoints match.

---

## 10. Definition of Success

The implementation is successful when it can ingest representative land–atmosphere papers and answer realistic location-specific questions while:

- preserving exact provenance;
- keeping environmental Context explicit;
- retrieving semantically analogous studies despite different terminology;
- rejecting or down-ranking environmentally incompatible evidence;
- preserving contradictions and sign reversals;
- handling spatial configuration correctly;
- producing context-coherent mechanism paths;
- giving readable answers with direct scientific references;
- exposing the similarity and ranking reasoning in inspectable JSON.

The detailed algorithms, prompts, schemas, validation rules, and tunable parameters are defined in the accompanying **indexing** and **query** pipeline specifications.
