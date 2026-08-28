# Land–Atmosphere Knowledge Graph: Detailed Indexing Pipeline
## PDF → structured evidence → context-aware scientific graph → embeddings → Neo4j

**Status:** implementation-ready specification  
**Revision:** 2026-08-19 — implementation-resolution + corpus stress-test + field-specification pass: exact candidate retrieval, evidence bundling, semantic consolidation, enrichment, canonicalization, retry/abstention, ingest algorithms, conditioning-Facet adjudication, paper-derived edge cases, and normative semantic/provenance field-writing guidance.  
**Primary generative model:** `qwen3.6:27b` through Ollama  
**Embedding family:** Qwen3-Embedding  
**PDF parser:** NVIDIA Nemotron-Parse v1.2  
**Graph store:** Neo4j  
**Algorithmic layer:** Python  
**Design goal:** a context-conditioned land–atmosphere knowledge graph that supports forward, backward, A→B, and global scientific reasoning queries.

---

# 1. Purpose

This document specifies exactly how to turn a scientific PDF into a validated, searchable graph suitable for questions such as:

- What kind of land-use change could increase rainfall in this watershed?
- How could dust storms be reduced here?
- What might happen if 20% of the forest is removed?
- How can intervention A influence outcome B?
- What mechanisms does the literature report globally?

The indexing pipeline must preserve three things simultaneously:

1. **Context** — where, when, and under what environmental/scenario conditions a finding holds.
2. **Mechanism/effect structure** — what scientific state is reported to affect another state.
3. **Evidence/provenance** — exactly which source passage supports each extracted object.

The graph is not intended to claim universal causality. It indexes **paper-supported claims scoped to the contexts or transitions in which they were reported**.

**Normative implementation note:** Sections 1–95 describe the architecture and stages; Section 96 gives the exact algorithms for every operation that would otherwise be ambiguous (`retrieve`, `select`, `merge`, `reconcile`, `deduplicate`, enrichment, canonicalization, retries). Section 96 overrides any less-specific shorthand earlier in the file.

---

# 2. Core design invariants

These are hard implementation rules.

## 2.1 The paper/context is the semantic unit; blocks are evidence units

Never treat an arbitrary token chunk as an independent study.

Stable blocks are generated for **every paper**, regardless of length, because they provide permanent evidence identifiers.

Chunking/evidence selection is only a context-window management technique.

---

## 2.2 One minimal scientific schema

Use only:

- `Paper`
- `Context`
- `Facet`
- `Transition`
- `Claim`
- `State`

and one technical provenance object:

- `SourceBlock`

Do not create separate "context graph", "evidence graph", "mechanism graph", "enrichment graph", etc. These are views over one property graph.

---

## 2.3 Rich context is represented as typed free-text Facets

Do not require scalar columns for wind, climate, soil, terrain, LULC, etc.

A valid Facet may be:

```json
{
  "domain": "atmosphere",
  "notion": "background wind regime",
  "description": "During JJAS the prevailing low-level flow is southwesterly, typically 4–8 m/s, moisture-bearing, and directionally persistent; pre-monsoon flow is weaker and more variable."
}
```

Numbers, ranges, units, categories, seasonality, spatial relationships, and descriptive information remain inside the description unless a later deterministic enrichment procedure creates a structured derived description.

`Facet` has no separate `scope` field. If a qualifier such as season, atmospheric layer, subregion, or time of day is part of the Facet's meaning, preserve it naturally in `description`. If the qualifier creates a genuinely different environmental/scenario state for multiple findings, represent that difference with a child `Context`.

---

## 2.4 Context inheritance prevents repetition

A child context stores only what differs from or specializes its parent.

Example:

```text
C1: Brazil, wet season, common atmospheric/terrain context
├── C1.1: forest control
└── C1.2: grassland scenario
```

At retrieval time:

```text
Effective(C1.1) = Facets(C1) ∪ Facets(C1.1)
Effective(C1.2) = Facets(C1) ∪ Facets(C1.2)
```

Do not physically copy inherited facets onto children.

---

## 2.5 A result usually scopes to a Context or Transition

A `Claim` must reference the context or transition for which the paper supports it.

If the result concerns a contrast such as forest → grassland, scope it to the `Transition`.

If it describes a state without a comparison, scope it to the relevant `Context`.

---

## 2.6 No LLM confidence scores

Never ask the extraction model to assign scientific confidence probabilities.

Store observable evidence and provenance instead.

At query time, compute retrieval/applicability scores algorithmically. Do not present them as probabilities of scientific truth.

---

## 2.7 Reported and derived context are never destructively merged

Paper-reported context and raster/reanalysis-derived context can coexist.

If they disagree, preserve both.

---

## 2.8 Under-merge rather than over-merge

When uncertain whether two scientific concepts are identical, keep them separate.

Examples:

- `ET` and `evapotranspiration`: usually safe to merge.
- `evapotranspiration` and `latent heat flux`: related but not identical.
- `moisture recycling` and `moisture convergence`: distinct.

Over-merging corrupts graph semantics. Under-merging is recoverable by semantic retrieval.

---

# 3. Recommended project layout

```text
project/
├── config/
│   ├── pipeline.yaml
│   ├── prompt_versions.yaml
│   └── state_aliases.yaml
│
├── prompts/
│   ├── paper_map.txt
│   ├── section_scout.txt
│   ├── map_consolidation.txt
│   ├── facet_extraction.txt
│   ├── claim_extraction.txt
│   ├── context_reconciliation.txt
│   ├── paper_consolidation.txt
│   └── state_adjudication.txt
│
├── schemas/
│   ├── source_block.schema.json
│   ├── paper_map.schema.json
│   ├── facet_batch.schema.json
│   ├── claim_batch.schema.json
│   ├── final_paper.schema.json
│   └── ...
│
├── data/
│   └── papers/
│       └── P000123/
│           ├── source/
│           │   └── paper.pdf
│           ├── parse/
│           │   ├── nemotron_raw.json
│           │   └── nemotron.md
│           ├── clean/
│           │   └── cleaned.md
│           ├── blocks/
│           │   ├── blocks.jsonl
│           │   └── block_embeddings.npy
│           ├── extraction/
│           │   ├── map/
│           │   ├── facets/
│           │   ├── claims/
│           │   ├── reconciliation/
│           │   └── consolidated.json
│           ├── enrichment/
│           │   └── enrichment.json
│           ├── spatial/
│           │   └── C001.geojson
│           ├── final/
│           │   └── final_paper.json
│           └── manifest.json
│
└── src/
    ├── parse/
    ├── clean/
    ├── extract/
    ├── enrich/
    ├── embeddings/
    ├── canonicalize/
    ├── graph/
    └── validate/
```

The filesystem/object store is the reproducible archive.

Neo4j contains the **active materialized searchable graph**.

---

# 4. Configuration

Create a single configuration object. Do not scatter these values across code.

```yaml
paper_mapping:
  whole_paper_threshold_tokens: 15000
  map_consolidation_source_budget_tokens: 9000
  evidence_input_budget_tokens: 18000
  hard_llm_input_budget_tokens: 24000

ollama:
  model: "qwen3.6:27b"
  retries: 2
  structured_output: true
  stages:
    paper_map: {temperature: 0.1, thinking: low}
    section_scout: {temperature: 0.0, thinking: no}
    facet_extraction: {temperature: 0.0, thinking: no}
    claim_extraction: {temperature: 0.0, thinking: low}
    context_reconciliation: {temperature: 0.0, thinking: medium}
    paper_consolidation: {temperature: 0.0, thinking: medium}
    state_adjudication: {temperature: 0.0, thinking: low}

embeddings:
  model: "Qwen3-Embedding"
  dimension: 2048
  normalize: true
  block_embeddings: true

blocks:
  max_block_tokens: 1500
  target_split_tokens: 1100

section_scout:
  target_tokens: 6500
  min_tokens: 3500
  max_tokens: 8000

evidence_retrieval:
  lexical_top_k: 10
  semantic_top_k: 10
  neighbor_blocks_each_side: 1
  max_context_bundle_blocks: 80
  bm25_k1: 1.5
  bm25_b: 0.75

consolidation:
  facet_notion_candidate_cosine: 0.82
  facet_content_candidate_cosine: 0.88
  claim_endpoint_candidate_cosine: 0.88
  max_context_reconciliation_rounds: 2

enrichment:
  min_valid_polygon_coverage: 0.80
  wind_directional_persistence_threshold: 0.55

graph:
  neo4j_uri: "bolt://localhost:7687"
  database: "neo4j"

canonicalization:
  state_embedding_top_k: 5
  auto_merge_cosine_threshold: null
  # Intentionally null initially. Exact aliases only are auto-merged.
```

### Important

`15000` tokens is a routing default, not a scientific constant.

Tune it empirically using extraction accuracy and GPU throughput.

---

# 5. Canonical IDs

Never use database-internal IDs as scientific identifiers.

Use deterministic paper-scoped IDs.

```text
Paper       P000123
Context     P000123_C001
Facet       P000123_F001
Transition  P000123_T001
Claim       P000123_CL001
SourceBlock P000123:S02:P0014
```

Canonical cross-paper `State` IDs should be generated from the canonical concept/state pair or UUID:

```text
state::evapotranspiration::decrease
state::precipitation::decrease
```

If canonicalization changes, use a stable UUID internally and keep the readable key as a property.

---

# 6. Scientific object schemas

The examples below describe the canonical structure. Implement them as Pydantic models and export JSON Schema to Ollama.

---

## 6.1 Paper

```json
{
  "id": "P000123",
  "title": "Example Paper",
  "doi": null,
  "year": 2019,
  "source_file": "paper.pdf"
}
```

Required:

- `id`
- `title`
- `source_file`

Optional:

- `doi`
- `year`

---

## 6.2 SpatialSupport

```json
{
  "kind": "point",
  "name": "Example Flux Tower",
  "geometry": {
    "type": "Point",
    "coordinates": [-60.02, -3.11]
  },
  "resolution": "exact"
}
```

Allowed `kind`:

```text
point
patch
watershed
region
climate_zone
global
unresolved
```

Allowed `resolution`:

```text
exact
approximate
named_region
global
unresolved
```

Rules:

- Do not invent coordinates.
- Broad named regions are not automatically represented by a centroid.
- Geometry is optional.
- A Context without resolvable spatial support remains valid.

---

## 6.3 Context

```json
{
  "id": "P000123_C001",
  "paper_id": "P000123",
  "parent_ids": [],
  "label": "Central Amazon wet-season common context",
  "aliases": [
    "study domain",
    "Amazon experiment"
  ],
  "spatial_support": {
    "kind": "region",
    "name": "Central Amazon",
    "geometry": null,
    "resolution": "named_region"
  },
  "evidence_block_ids": [
    "P000123:S02:P0014"
  ]
}
```

`aliases` are paper-local names used to find references elsewhere in the paper.

---

## 6.4 Facet

```json
{
  "id": "P000123_F001",
  "context_id": "P000123_C001",
  "domain": "atmosphere",
  "notion": "background wind regime",
  "description": "During the wet season, low-level flow is predominantly easterly and transports humid air into the domain.",
  "origin": "reported",
  "source": {
    "type": "paper",
    "id": "P000123"
  },
  "evidence_block_ids": [
    "P000123:S02:P0016"
  ]
}
```

Allowed `domain`:

```text
spatial_configuration
land_surface
hydrology
atmosphere
climate
substrate_terrain
other
```

Allowed `origin`:

```text
reported
derived
```

Required:

- `id`
- `context_id`
- `domain`
- `notion`
- `description`
- `origin`

Optional:

- `evidence_block_ids` for derived facets if source is an external dataset
- external source metadata

### Facet granularity rule

One facet = one coherent scientific notion.

Correct:

```text
notion = "background wind regime"
description = direction + speed + moisture character + seasonality
```

Do not obligatorily atomize it into wind speed, wind direction, moisture source, etc.

Split only when the source clearly describes genuinely distinct regimes or notions.

For `spatial_configuration`, preserve scientifically meaningful geometry and directional language in the description when reported, including terms such as:

```text
upwind / downwind
windward / leeward
patch edge / interior
patch size or heterogeneity scale
orientation relative to prevailing flow
distance-decay or remote influence
source region / sink region / precipitationshed
```

Do not infer these relationships from a map unless a validated spatial/vision procedure is explicitly used.

---

## 6.5 Transition

```json
{
  "id": "P000123_T001",
  "paper_id": "P000123",
  "from_context_id": "P000123_C002",
  "to_context_id": "P000123_C003",
  "label": "forest-to-pasture experiment",
  "aliases": [
    "EXP1",
    "deforestation experiment"
  ],
  "description": "Approximately 30% of the modeled forest area was replaced by pasture.",
  "evidence_block_ids": [
    "P000123:S03:P0027"
  ]
}
```

A Transition represents the comparison/intervention whose consequences are studied.

If an observational study compares two existing states rather than performing an intervention, the object may still be a Transition/comparison, but Claims should be `associative` unless causal attribution is justified by the paper.

---

## 6.6 ClaimEndpoint

```json
{
  "concept": "evapotranspiration",
  "state": "decrease"
}
```

Both strings use open vocabulary during paper extraction.

Canonicalization occurs after consolidation.

---

## 6.7 Claim

```json
{
  "id": "P000123_CL001",
  "paper_id": "P000123",
  "scope_type": "transition",
  "scope_id": "P000123_T001",
  "from": {
    "concept": "evapotranspiration",
    "state": "decrease"
  },
  "to": {
    "concept": "atmospheric moisture supply",
    "state": "decrease"
  },
  "relation": "causal",
  "description": "Reduced evapotranspiration lowers atmospheric moisture supply in the deforestation experiment.",
  "evidence_role": "OWN_RESULT",
  "conditioning_facet_ids": [
    "P000123_F004",
    "P000123_F009"
  ],
  "evidence_block_ids": [
    "P000123:S05:P0071"
  ]
}
```

Allowed `scope_type`:

```text
context
transition
```

Allowed `relation`:

```text
causal
associative
```

Extraction-control `evidence_role`:

```text
OWN_RESULT
AUTHORS_INTERPRETATION_OF_OWN_RESULT
CITED_BACKGROUND
HYPOTHESIS_OR_PROPOSAL
```

Only the first two are ingested as Claims. The field may be retained in the audit JSON even if omitted from Neo4j.

No confidence field.

`conditioning_facet_ids` is optional and may be empty. It references existing Context Facets that the paper specifically indicates are important for interpreting or transferring this Claim. It does **not** create a second kind of Facet.

Rules:

- reference only Facets attached to the Claim's scoped Context, inherited ancestors, or the FROM/TO Contexts of its scoped Transition;
- include a Facet only when supplied evidence makes its conditioning role explicit or clearly material;
- do not list every Facet in the Context by default;
- an empty list means "no specific conditioning Facets were isolated", not "context does not matter";
- query-time code may use these IDs for explainable reranking, but they are not hard scientific requirements unless a later benchmark justifies that policy.

---

## 6.8 State

Created after Claim consolidation/canonicalization.

```json
{
  "id": "state::evapotranspiration::decrease",
  "concept": "evapotranspiration",
  "state": "decrease",
  "aliases": [
    "ET decrease"
  ]
}
```

States are cross-paper graph nodes.

Contexts are never globally merged.

---

## 6.9 SourceBlock

```json
{
  "id": "P000123:S02:P0016",
  "paper_id": "P000123",
  "order": 41,
  "page": 5,
  "section_path": [
    "2 Methods",
    "2.1 Study Area"
  ],
  "block_type": "paragraph",
  "text": "During the wet season ...",
  "source_locator": {
    "page": 5
  }
}
```

Allowed `block_type`:

```text
title
abstract
heading
paragraph
list
table
table_caption
figure_caption
equation
footnote
reference
other
```

---


## 6.10 Normative field-writing specifications

These are **soft semantic-writing targets**, not hard token/word validators. The implementation must never invent, pad, or omit scientifically important information merely to satisfy a length target. When the evidence is genuinely brief, keep the field brief; when an essential qualifier requires extra words, preserve it.

| Field | Writing specification |
|---|---|
| `Context.label` | Concise human-readable noun phrase, usually **3–12 words**. Identify the study/scenario state, not the paper's result. Prefer wording grounded in the paper. |
| `Context.aliases[]` | Paper-local names, abbreviations, experiment IDs, or near-verbatim labels used to refer to that Context. Usually **1–8 words each**. Do not create generic semantic synonyms merely for retrieval. |
| `SpatialSupport.name` | Use the paper-, registry-, or gazetteer-supported place/site/region name. Do not add geographic specificity that is not supported. |
| `Facet.notion` | Short open-vocabulary scientific noun phrase, usually **2–8 words**. It names *what aspect is being described*, not its full value/state. Avoid complete sentences and avoid stuffing magnitude/season/direction into the notion when those belong in `description`. |
| `Facet.description` | Usually **20–60 words**. Write one self-contained, evidence-faithful description of the coherent notion. Preserve scientifically important quantities, ranges, units, direction, seasonality, layer, spatial configuration, and qualifications. It may exceed 60 words when needed for a genuinely complex but still single notion. If multiple independently retrievable notions are present, split the Facet instead. |
| `Transition.label` | Concise comparison/intervention name, usually **2–10 words**. Example: `forest-to-pasture experiment`. |
| `Transition.aliases[]` | Paper-local experiment/scenario names and abbreviations, usually **1–8 words each**. |
| `Transition.description` | Usually **10–50 words**. State what changed from FROM to TO, preserving reported magnitude, replacement type, timing, spatial arrangement, or experimental manipulation when material. Do not describe downstream outcomes here. |
| `ClaimEndpoint.concept` | Compact scientific noun phrase, usually **1–8 words**. Represent the variable/process/entity identity only; keep direction, magnitude, season, location, and causal language out of the concept when possible. |
| `ClaimEndpoint.state` | Compact directional/categorical state, usually **1–5 words**: e.g. `increase`, `decrease`, `higher`, `lower`, `earlier onset`, `no detectable change`. Keep detailed qualifiers in the Claim description. |
| `Claim.description` | Usually **15–50 words**. State the supported relationship and preserve only the qualifiers needed to interpret it correctly: magnitude, season/time-of-day, spatial direction/extent, threshold, wind regime, non-monotonicity, or other material conditionality. It may exceed 50 words for genuinely conditional/non-monotonic findings. Do not repeat the whole Context. |
| `State.aliases[]` | Common abbreviations or lexical variants of the same canonical concept/state. Do not include contextual qualifiers that would change the State's identity. |
| `evidence_block_ids[]` | Use the **smallest sufficient set of exact SourceBlocks** that directly supports the object. Deduplicate IDs and preserve paper order. Do not attach a whole evidence bundle merely because it was shown to the LLM. Reported Facets/Contexts/Transitions/ingested Claims require at least one direct evidence block. |
| `source` / external provenance | For reported objects, identify the paper. For derived Facets, record dataset/product, version where available, algorithm/method version, temporal window, and geometry/object used for derivation. Provenance is not semantic content and is not embedded. |
| `SourceBlock.text` | Exact cleaned source text for that evidence block. Never summarize or rewrite it. |

Additional rules:

1. Length ranges are **guidance for extraction consistency**, not acceptance thresholds.
2. Never add generic explanatory prose merely to make a description longer.
3. Prefer one precise sentence; use two only when needed to preserve a coherent complex condition.
4. `notion` and endpoint `concept` should be semantically stable enough to embed and compare; the rich scientific state belongs primarily in `description`.
5. Numeric values should normally remain in descriptions rather than being encoded into `notion`, `concept`, or canonical `State` identity.
6. When a finding changes sign/null state across season, time-of-day, region, wind regime, or experiment and those strata scope different findings, use the Context-splitting rule rather than writing one overstuffed description.
7. Evidence lists are provenance, not recall buckets: include only blocks that directly support the stored object, even if many additional blocks were retrieved into the LLM evidence bundle.

# 7. Stage 0 — paper registration

## Input

A PDF.

## Algorithm

1. Compute SHA-256 hash of PDF bytes.
2. Check registry for an existing identical hash.
3. If present:
   - do not index again;
   - link any new external metadata to the existing `Paper`.
4. If absent:
   - assign new `paper_id`;
   - create paper directory;
   - copy original PDF unchanged;
   - initialize `manifest.json`.

Example manifest:

```json
{
  "paper_id": "P000123",
  "pdf_sha256": "...",
  "status": "registered",
  "parser": "nemotron-parse-v1.2",
  "extractor_model": "qwen3.6:27b",
  "embedding_model": "qwen3-embedding",
  "active_pipeline_version": "0.1"
}
```

---

# 8. Stage 1 — PDF parsing with NVIDIA Nemotron-Parse v1.2

Use Nemotron-Parse v1.2 as the primary PDF parser.

The parser output should preserve as much as available:

- text
- reading order
- semantic class
- page number
- tables
- figure/table captions
- equations
- bounding boxes if available

Store both:

```text
parse/nemotron_raw.json
parse/nemotron.md
```

Never overwrite the raw parser output during cleaning.

## Parse validation

After parsing, validate:

```text
number_of_pages_parsed > 0
non_whitespace_text_length > minimum
page_count approximately matches PDF page count
```

Flag:

```text
PARSE_EMPTY
PARSE_PARTIAL
PARSE_PAGE_MISMATCH
PARSE_ENCODING_ERROR
```

Do not continue automatic extraction on an empty/obviously corrupted parse.

## Figures

For v1, retain:

- figure caption
- figure label
- nearby referring paragraphs

Do not infer scientific values from the figure image unless a separate validated vision pipeline is added.

## Tables

Preserve table structure whenever possible.

Never flatten a table by deleting row/column relationships solely to reduce token count.

---

# 9. Stage 2 — Markdown cleaning

The cleaner must be deterministic.

Input:

```text
parse/nemotron.md
```

Output:

```text
clean/cleaned.md
```

## 9.1 Cleaning operations

Apply in this order.

### A. Unicode normalization

Use NFC normalization.

Normalize obvious typographic whitespace.

Preserve scientific symbols:

```text
Δ
λ
θ
α
μ
±
≤
≥
°
```

Do not transliterate them away.

---

### B. Remove repeated page headers/footers

Only remove a line if:

1. it occurs on a high fraction of pages, e.g. `>= 0.6`, and
2. it appears near the top or bottom of those pages, and
3. it is not a section heading or scientific content.

Never remove a repeated phrase merely because it appears often in body text.

---

### C. Repair line-wrap hyphenation conservatively

Join:

```text
evapo-
transpiration
```

only when the hyphen is a line-break artifact.

Do not join true compounds:

```text
land-atmosphere
soil-moisture
```

If uncertain, preserve the original form.

---

### D. Normalize whitespace

- collapse repeated spaces
- preserve paragraph breaks
- preserve headings
- preserve list boundaries
- preserve table boundaries
- preserve captions
- preserve equations

---

### E. Reference section marking

Detect bibliography heading:

```text
References
Bibliography
Literature Cited
```

Mark subsequent reference entries as `reference` blocks.

Do not use reference entries as scientific evidence for Claims.

---

### F. Keep in-text citations

Do not remove:

```text
(Smith et al., 2019)
[23]
```

They may help distinguish the current paper's finding from background literature during extraction.

---

# 10. Stage 3 — stable SourceBlock generation

**Always run this stage.**

This is independent of the 15k-token routing threshold.

## 10.1 Goal

Convert cleaned Markdown into stable, ordered evidence blocks.

## 10.2 Block boundaries

Prefer semantic boundaries:

1. heading
2. paragraph
3. list item/group
4. table
5. figure caption
6. table caption
7. displayed equation

Do not create arbitrary 500-token blocks if a coherent paragraph is available.

## 10.3 Oversized paragraph/table handling

If a single block exceeds `MAX_BLOCK_TOKENS`, e.g. 1500:

- paragraph: split at sentence boundaries;
- table: split by contiguous row groups while repeating the header;
- never split a mathematical expression from its immediately explanatory sentence if avoidable.

Suffix IDs:

```text
P000123:S04:P0037:A
P000123:S04:P0037:B
```

## 10.4 IDs

Generate stable IDs from paper + section ordinal + block ordinal.

Do not derive IDs from raw text hashes alone because minor parser changes would make debugging difficult.

Maintain `order` for original paper order.

## 10.5 Save

Write:

```text
blocks/blocks.jsonl
```

One JSON object per `SourceBlock`.

---

# 11. Stage 4 — paper length routing

Estimate token count using the closest available tokenizer to the extraction model.

Let:

```text
T = useful tokens excluding bibliography
```

Default routing:

```text
if T <= 15000:
    whole-paper mapping
else:
    section-scout mapping
```

This threshold is configurable.

The objective is not to maximize context usage. Reserve room for:

- system prompt
- JSON Schema
- context registry
- model output
- safety margin

For a nominal 32k working context, detailed evidence calls should normally keep raw evidence below roughly 18k tokens.

---

# 12. Stage 5A — whole-paper mapping for short papers

## Purpose

Discover:

- Contexts
- parent/child hierarchy
- spatial support
- paper-local aliases
- Transitions
- which source blocks likely contain Context details
- which source blocks likely contain Results/Claims

Do **not** extract detailed Facets or Claims yet.

## Input

- title/metadata
- cleaned paper with stable SourceBlock IDs
- no bibliography unless necessary

## Prompt: `paper_map.txt`

The exact standalone Qwen3.6-27B prompt is versioned as `paper_map_v10` in `prompts/paper_map.txt`. It must:

- define a study setting, inheritance, complete effective setting, and comparison without assuming project knowledge;
- implement the complete-setting tree algorithm in Section 97.9;
- explain every input and output field;
- preserve paper-local names for separately reported study units;
- use no benchmark-paper names or identifiers;
- return only schema-valid JSON.

## Paper-map output schema

```json
{
  "contexts": [
    {
      "temp_id": "C1",
      "label": "common Amazon wet-season context",
      "parent_temp_ids": [],
      "split_reason": null,
      "aliases": ["study domain"],
      "spatial_support": {
        "kind": "region",
        "name": "Central Amazon",
        "geometry": null,
        "resolution": "named_region"
      },
      "evidence_block_ids": ["P000123:S02:P0014"],
      "facet_seed_block_ids": ["P000123:S02:P0014", "P000123:S02:P0016"]
    }
  ],
  "transitions": [
    {
      "temp_id": "T1",
      "from_context_temp_id": "C1.1",
      "to_context_temp_id": "C1.2",
      "label": "forest to pasture scenario",
      "aliases": ["EXP1"],
      "description": "Forest is replaced by pasture.",
      "evidence_block_ids": ["P000123:S03:P0027"],
      "claim_seed_block_ids": ["P000123:S04:P0041"]
    }
  ],
  "global_claim_seed_block_ids": [],
  "ambiguities": []
}
```

Validate all returned block IDs against `blocks.jsonl`.

---

# 13. Stage 5B — section scouts for long papers

For papers over the mapping threshold, do **not** independently extract graph objects from arbitrary chunks.

Instead, run low-cost structure scouts over semantic sections.

## 13.1 Section grouping

Group stable blocks by top-level or second-level heading.

Target approximately:

```text
4000–8000 tokens per scout input
```

If a section is larger, split by subsection or paragraph groups.

## 13.2 Scout purpose

The scout does not create final Contexts.

It identifies:

- Context/scenario names mentioned
- location names
- experiment/control names
- aliases
- possible transitions
- block IDs likely important for context extraction
- block IDs likely important for claim extraction
- cross-references such as "EXP2", "control case", "Fig. 5"

## Prompt: `section_scout.txt`

The exact standalone Qwen3.6-27B prompt is versioned as `section_scout_v4` in `prompts/section_scout.txt`. A separately named site, season, control, treatment, complete model run, or experimental case is emitted as one mention. When its paper-local name combines several variables, the scout preserves that complete name instead of collapsing several named runs into one family mention. A code denoting only one variable value reused by several complete runs is retained as Facet evidence, not emitted as a standalone setting mention.

## Scout schema

```json
{
  "context_mentions": [
    {
      "name": "EXP2",
      "description": "50% deforestation experiment",
      "block_ids": ["..."]
    }
  ],
  "location_mentions": [],
  "comparison_mentions": [],
  "facet_seed_block_ids": [],
  "claim_seed_block_ids": [],
  "cross_references": [],
  "ambiguities": []
}
```

---

# 14. Stage 6 — consolidate scouts into one paper map

Input:

- all scout outputs
- title + abstract
- experiment/method section blocks where possible
- no detailed extraction

## Prompt: `map_consolidation.txt`

The exact standalone Qwen3.6-27B prompt is versioned as `map_consolidation_v10` in `prompts/map_consolidation.txt`. It has the same complete-setting requirements as `paper_map_v10`, and additionally explains the distinction between preliminary scout notes and selected original evidence.

The output schema is the same `paper_map` schema used for short papers.

---

# 15. Stage 7 — assign permanent Context/Transition IDs

After the map validates:

1. topologically sort Context hierarchy;
2. assign permanent IDs:
   - `P000123_C001`
   - `P000123_C002`
3. assign Transition IDs;
4. build `context_registry.json`.

Example:

```json
{
  "P000123_C001": {
    "label": "common study context",
    "parent_ids": [],
    "aliases": ["study domain"]
  },
  "P000123_C002": {
    "label": "forest control",
    "parent_ids": ["P000123_C001"],
    "aliases": ["CTRL", "control", "forest"]
  }
}
```

The Context Registry is passed to later LLM calls.

---

# 16. Stage 8 — optional block embeddings for within-paper evidence retrieval

For long or complex papers, embed SourceBlock text with Qwen3-Embedding.

This is a temporary/internal extraction index. It may be persisted on disk.

Do not need to create a Neo4j vector index for SourceBlocks initially.

## Stored block text

Embed:

```text
Section: {section_path}
Type: {block_type}
Text: {text}
```

Normalize vectors.

Build a local FAISS/numpy index or simple matrix search because each paper is small.

---

# 17. Stage 9 — Context evidence-bundle construction

Detailed Facet extraction does not consume anonymous chunks. It consumes an **evidence bundle for one known Context**.

## 17.1 Inputs

For target Context `C`:

- Context Registry
- map `facet_seed_block_ids`
- aliases of `C`
- aliases of parent/children when useful
- SourceBlocks
- optional SourceBlock embeddings

## 17.2 Candidate generation

Create deterministic search strings:

```text
{context label}
{aliases}
study area
location
climate
season
meteorology
wind
atmospheric
land cover
land use
vegetation
hydrology
soil moisture
soil
terrain
topography
elevation
spatial configuration
patch
heterogeneity
management
```

Then:

1. include all map seed blocks;
2. lexical search SourceBlocks for aliases and keywords;
3. semantic search SourceBlock embeddings;
4. union results;
5. add one neighboring block before and after each selected paragraph where available;
6. remove bibliography blocks;
7. deduplicate by block ID;
8. preserve original paper order.

## 17.3 Priority score

For token-budget trimming, assign:

```text
100  map seed block
80   exact target-context alias match
70   Methods/Study Area/Experimental Design section
60   semantic top-k
50   lexical keyword match
40   neighboring context block
```

When over budget:

- sort by priority descending;
- retain coherent adjacent groups;
- then restore original paper order before sending to the LLM.

## 17.4 Evidence budget

Default:

```text
<= 18000 evidence tokens
```

If exceeded, split by semantic domain:

```text
A: climate + atmosphere + hydrology
B: land_surface + spatial_configuration
C: substrate_terrain + other
```

Every sub-call still receives:

- target Context
- Context Registry
- already extracted facets for the target
- parent facets where relevant

---

# 18. Stage 10 — Facet extraction

Run one or more calls per Context evidence bundle.

## Prompt: `facet_extraction.txt`

```text
SYSTEM

You extract LOCAL Context Facets from land-atmosphere scientific papers.

A Facet describes one coherent aspect of the environmental/scenario
Context.

Allowed domains:
- spatial_configuration
- land_surface
- hydrology
- atmosphere
- climate
- substrate_terrain
- other

Each Facet contains:
- domain
- notion: short open-vocabulary scientific noun phrase, usually 2–8 words;
- description: faithful information-rich description, usually 20–60 words;
- evidence SourceBlock IDs.

The word ranges are soft targets. Never invent or pad information to hit them.
A shorter description is correct when the evidence is simple; a longer one is
correct when essential qualifiers make one coherent notion genuinely complex.

Important representation rule:
A Facet can remain richly descriptive. Preserve useful quantities,
ranges, units, directions, seasonality, spatial relationships, and
qualifications inside the description. Do not force a descriptive
scientific variable into one scalar.

Hard rules:
1. Use only supplied source passages.
2. Do not add outside scientific or geographic knowledge.
3. Do not infer enrichment variables such as Köppen class, aridity,
   terrain metrics, soil class, or climatological wind unless the paper
   itself reports them.
4. Do not normalize units.
5. Do not create numerical values that are not reported.
6. Extract only LOCAL facets belonging to the target Context.
7. Do not repeat facets inherited unchanged from parent Contexts.
8. If the child explicitly differs from the parent, extract the
   child-specific difference.
9. One Facet = one coherent notion, not necessarily one scalar.
10. Do not split a rich wind regime into speed/direction/moisture/season
    unless the source presents genuinely distinct regimes that need
    independent retrieval.
11. There is no separate Facet scope field. Preserve season, atmospheric
    layer, time of day, subregion, spatial scale, and similar qualifiers
    inside the description. If they define a genuinely separate Context,
    emit an unmapped_context_hint instead.
12. For spatial_configuration, preserve reported upwind/downwind,
    windward/leeward, edge/interior, patch-scale, orientation, distance,
    and source/sink relationships when present. Do not infer them.
13. Every reported Facet must cite at least one exact SourceBlock ID.
14. origin is "reported".
15. Do not assign confidence scores.
16. If the text appears to describe a Context not present in the
    registry, emit an unmapped_context_hint instead of silently
    attaching it to the target.
17. Keep `notion` concise and value-free where possible; put magnitude,
    direction, season, layer, and detailed state in `description`.
18. Aim for a 20–60 word description without padding or dropping material
    qualifiers. Split only when there are multiple coherent notions.
19. Return only schema-valid JSON.

USER

Paper:
{paper_id}

Target Context:
{target_context}

Context Registry:
{context_registry}

Parent effective Facets already known:
{parent_facets}

Existing local Facets for target:
{existing_target_facets}

Evidence bundle:
{evidence_blocks}
```

## Facet extraction output schema

```json
{
  "context_id": "P000123_C001",
  "facets": [
    {
      "domain": "atmosphere",
      "notion": "background wind regime",
      "description": "During the wet season, low-level flow is predominantly easterly and humid.",
      "evidence_block_ids": ["P000123:S02:P0016"]
    }
  ],
  "unmapped_context_hints": [],
  "ambiguities": []
}
```

After validation, assign permanent Facet IDs.

---

# 19. Stage 11 — Transition/Claim evidence-bundle construction

Claims require different evidence than Context Facets.

For each Transition `T`:

## 19.1 Seeds

Include:

- Transition map evidence blocks
- `claim_seed_block_ids`
- from/to Context aliases
- Transition aliases

## 19.2 Search terms

Use deterministic query terms:

```text
{transition label}
{transition aliases}
{from context aliases}
{to context aliases}
effect
response
difference
change
increase
decrease
mechanism
because
due to
caused
associated
result
sensible heat
latent heat
evapotranspiration
soil moisture
PBL
boundary layer
cloud
precipitation
convergence
circulation
temperature
humidity
wind
dust
aerosol
```

Do not assume this keyword list defines the ontology; it only improves source retrieval.

## 19.3 Prefer sections

Prioritize:

```text
Results
Discussion
Mechanism
Sensitivity
Experiment
Analysis
Conclusions
```

Also include the experimental-design blocks defining the Transition.

## 19.4 Neighbor expansion

Add ±1 adjacent block around selected Results/Discussion paragraphs.

## 19.5 Token budget

Same default:

```text
<= 18000 evidence tokens
```

If too large, split by outcome/mechanism family while preserving the same `scope_id`.

For example:

```text
T1 / surface energy
T1 / hydrology
T1 / boundary layer
T1 / clouds and precipitation
T1 / circulation
```

---

# 20. Stage 12 — Claim extraction

## Prompt: `claim_extraction.txt`

```text
SYSTEM

You extract evidence-backed scientific relationships from a
land-atmosphere research paper.

Each Claim represents ONE paper-supported relationship:

FROM {concept, state}
    -- relation -->
TO   {concept, state}

Endpoint `concept` should usually be a compact 1–8 word scientific noun
phrase. Endpoint `state` should usually be a compact 1–5 word directional or
categorical state. Claim `description` should usually be 15–50 words. These
are soft targets: never invent, pad, or omit material qualifiers to meet them.

Allowed relation:
- causal
- associative

Use "causal" only when:
- the paper explicitly attributes an effect/response to the source
  condition or process; OR
- the experimental perturbation directly supports that interpretation.

Use "associative" for:
- correlation;
- spatial/temporal co-occurrence;
- statistical association;
- observational preference;
- relationships where causal attribution is not established.

Hard rules:
1. Extract only relationships supported by supplied source passages.
2. Never add an intermediate mechanism merely because it is
   scientifically plausible.
3. Split a multi-step mechanism chain only if each individual step is
   supported by the supplied text.
4. Preserve competing pathways as separate Claims.
5. Preserve null effects as Claims when scientifically meaningful.
6. Preserve opposite effects rather than reconciling them.
7. Preserve qualifiers in the Claim description: season, scale,
   location, magnitude, threshold, timing, wind regime, etc.
8. Do not merge physically different outcome variables.
   Example: LST != 2-m air temperature.
9. Do not convert a cited background claim into this paper's own finding
   unless the authors explicitly adopt/test it in the study.
10. scope_id must be one known Context or Transition.
11. If the true scope is not in the Context Registry, emit an
    unmapped_context_hint.
12. Every Claim must cite exact SourceBlock IDs.
13. Do not assign confidence scores.
14. Do not decide whether the Claim is universally true.
15. Return `evidence_role` for every candidate using exactly one of:
    OWN_RESULT, AUTHORS_INTERPRETATION_OF_OWN_RESULT, CITED_BACKGROUND,
    HYPOTHESIS_OR_PROPOSAL. Only the first two are ingestible Claims.
16. `conditioning_facet_ids` may reference existing Context Facets that
    supplied evidence specifically indicates are important to this Claim's
    interpretation or transferability. Do not attach every Context Facet.
17. If no particular conditioning Facets are supported, return an empty list.
18. Keep endpoint concepts free of season/location/magnitude when possible;
    preserve such qualifiers in the Claim description or scoped Context.
19. Keep endpoint states compact. Do not create highly specific canonical-like
    states such as "increase by 3–4 C at night"; use `increase` and preserve
    the magnitude/time qualifier in `description`.
20. Aim for a 15–50 word Claim description without padding. It may be longer
    when required to preserve conditional, spatial, or non-monotonic behavior.
21. Return only schema-valid JSON.

USER

Paper:
{paper_id}

Known Context Registry:
{context_registry}

Known Transitions:
{transitions}

Available effective Facets for the target scope:
{available_scope_facets}

Target scope:
{target_scope}

Evidence bundle:
{evidence_blocks}
```

## Claim output schema

```json
{
  "scope_id": "P000123_T001",
  "claims": [
    {
      "from": {
        "concept": "evapotranspiration",
        "state": "decrease"
      },
      "to": {
        "concept": "atmospheric moisture supply",
        "state": "decrease"
      },
      "relation": "causal",
      "description": "Reduced evapotranspiration lowers atmospheric moisture supply in the deforestation experiment.",
      "evidence_role": "OWN_RESULT",
      "conditioning_facet_ids": ["P000123_F004"],
      "evidence_block_ids": ["P000123:S05:P0071"]
    }
  ],
  "unmapped_context_hints": [],
  "ambiguities": []
}
```

Assign permanent Claim IDs only after schema validation.

---

# 21. Claims not tied to a Transition

Some papers contain:

- observational associations within one site;
- theoretical relationships;
- general results without a baseline→scenario transition.

For such cases:

```text
scope_type = context
scope_id = relevant Context
```

Do not invent a Transition solely to satisfy the schema.

---

# 22. Multi-step sentences

Example source:

> Deforestation reduced ET, which lowered atmospheric moisture supply and reduced precipitation.

If all links are asserted by the source, extract:

```text
forest cover decrease → ET decrease
ET decrease → atmospheric moisture supply decrease
atmospheric moisture supply decrease → precipitation decrease
```

If the source only says:

> Deforestation reduced rainfall.

extract only:

```text
forest cover decrease → precipitation decrease
```

Never fill the middle from general knowledge.

---

# 23. Null results

Represent meaningful nulls explicitly.

Example:

```json
{
  "from": {
    "concept": "forest cover",
    "state": "decrease"
  },
  "to": {
    "concept": "precipitation",
    "state": "no detectable change"
  },
  "relation": "causal",
  "description": "The experiment found no statistically detectable precipitation response under the tested conditions."
}
```

Do not delete null results during consolidation.

They are important for context dependence.

---

# 24. Stage 13 — late Context hints and map reconciliation

Facet/Claim extraction may discover text that clearly belongs to a missing scenario.

Collect all:

```text
unmapped_context_hints
```

If none exist, continue.

If hints exist, run one reconciliation call.

## Prompt: `context_reconciliation.txt`

```text
SYSTEM

You are reconciling possible missing Contexts in a scientific paper.

You are given:
- the current Context Registry;
- extracted objects;
- raw evidence for new context hints.

For each hint decide exactly one:
1. ATTACH_TO_EXISTING_CONTEXT
2. ADD_CHILD_CONTEXT
3. ADD_INDEPENDENT_CONTEXT
4. IGNORE_AS_NOT_A_CONTEXT
5. UNRESOLVED

Rules:
- Do not use outside knowledge.
- Do not rewrite scientific findings.
- Do not create a Context solely for a repeated description.
- Add a Context only when it represents a scientifically distinct state
  that scopes findings or experimental conditions.
- Prefer parent-child inheritance when conditions are shared.
- Preserve uncertainty.
- Cite SourceBlock IDs.

Return only schema-valid JSON.

USER

Current Context Registry:
{context_registry}

Hints:
{hints}

Evidence:
{hint_evidence_blocks}
```

If the map changes:

1. update Context Registry;
2. reassign affected Facets/Claims;
3. rerun extraction only for newly created contexts/scopes;
4. do not rerun the entire paper automatically.

---

# 25. Stage 14 — deterministic pre-consolidation cleanup

Before the final consolidation LLM:

## 25.1 Exact deduplication

Remove exact duplicate candidate objects where all are identical:

- same scope/context
- same notion/concept pair
- same normalized description
- same evidence IDs

Merge evidence arrays.

## 25.2 ID validation

Every:

```text
context_id
parent_id
from_context_id
to_context_id
scope_id
evidence_block_id
```

must resolve.

## 25.3 Hierarchy validation

Reject:

- self-parent
- cycle in Context inheritance
- Transition from unknown Context
- Transition with identical from/to unless explicitly meaningful

Use topological sort to detect cycles.

---

# 26. Stage 15 — per-paper consolidation

One final LLM call receives **candidate objects**, not the entire raw paper.

Only include raw evidence for ambiguous collisions if required.

## Prompt: `paper_consolidation.txt`

```text
SYSTEM

You consolidate previously extracted scientific objects from ONE paper.

YOU ARE NOT PERFORMING NEW SCIENTIFIC EXTRACTION.

Allowed operations:
- merge duplicate Context candidates that clearly describe the same
  scientific state;
- finalize parent-child Context relationships;
- merge duplicate local Facets within the same Context;
- merge duplicate Claims with the same meaning AND same scope;
- preserve all evidence IDs from merged objects;
- repair references after merges;
- retain competing or contradictory Claims;
- flag unresolved conflicts.

Forbidden operations:
- introducing new Contexts, Facets, Claims, mechanisms, quantities, or
  scientific facts;
- using outside knowledge;
- moving a child-specific Facet to a parent unless the input evidence
  establishes that it applies to all children;
- merging Contexts that differ in a scientifically relevant state;
- merging Claims across different response variables, temporal scopes,
  spatial scopes, or counterfactuals;
- choosing one contradictory Claim and deleting another;
- assigning confidence scores;
- filling missing values;
- reconciling reported context against derived enrichment.

Inheritance rule:
A child stores LOCAL Facets only.
Effective retrieval context is computed later from ancestors + local
Facets.

Traceability rule:
Every finalized object must map to at least one candidate input object.

Return:
1. finalized Contexts
2. finalized Transitions
3. finalized Facets
4. finalized Claims
5. unresolved conflicts
6. provisional-to-final ID mapping

Return only schema-valid JSON.

USER

Paper:
{paper_metadata}

Context Registry:
{context_registry}

Candidate Facets:
{facet_candidates}

Candidate Claims:
{claim_candidates}

Candidate Transitions:
{transition_candidates}
```

---

# 27. Stage 16 — final paper validation

The consolidated paper must pass all checks before enrichment, embeddings, or graph writes.

## Required structural invariants

### Paper

- exactly one `Paper`
- valid `paper_id`

### Context

- every Context belongs to the Paper
- no Context inheritance cycle
- parent exists
- labels non-empty
- spatial support valid if present

### Facet

- valid domain
- non-empty notion
- non-empty description
- no separate `scope` field
- context exists
- `origin=reported`
- at least one evidence block for reported Facets

### Transition

- from/to Contexts exist
- evidence exists
- from/to are not accidentally identical

### Claim

- scope exists
- from concept/state non-empty
- to concept/state non-empty
- relation in `{causal, associative}`
- every `conditioning_facet_id`, if present, exists and is reachable from the scoped Context/Transition
- at least one evidence block exists
- evidence block belongs to same Paper

### Evidence

- every referenced block exists
- bibliography/reference blocks are not sole evidence for a Claim

## Semantic warning checks

Flag but do not necessarily reject:

```text
same description attached to many sibling Contexts
claim has unusually long concept string
facet notion looks like a full paragraph
large fraction of Claims come only from Introduction
causal Claim derived from observational correlation language
```

These warnings should enter QA logs.

---

# 28. Stage 17 — optional spatial resolution and environmental enrichment

This stage is optional.

Failure or inapplicability does not block graph indexing.

## 28.1 Resolution eligibility

Attempt enrichment only when spatial support is sufficiently actionable.

### Exact point

Use directly.

### Polygon/watershed/patch

Use geometry directly.

### Named local study area

May geocode or resolve to polygon/point.

Record resolution method.

### Broad region

Example:

```text
Amazon basin
Mediterranean region
global tropics
```

Do not sample one arbitrary centroid and pretend it represents the region.

Either:

- resolve an appropriate region polygon and compute distributions/zonal summaries; or
- skip local enrichment.

### Global/model-idealized

Skip local enrichment unless explicitly meaningful.

---

# 29. Enrichment provenance

Every derived Facet must store:

```json
{
  "origin": "derived",
  "source": {
    "type": "dataset",
    "name": "dataset-name",
    "version": "version/date",
    "method": "polygon zonal statistic"
  }
}
```

Never label an external dataset value as `reported`.

---

# 30. Initial enrichment families

Keep the first enrichment implementation small.

Recommended:

1. **climate regime**
2. **hydroclimatic/aridity regime**
3. **seasonal wind regime**
4. **terrain setting**
5. **land-surface/configuration**, when geometry supports it

Possible derived descriptions:

```text
climate | Köppen climate regime
"Approximately 82% of the resolved polygon falls within Aw..."

hydrology | aridity regime
"1991–2020 P/PET is approximately 0.48; the area is transitional..."

atmosphere | seasonal background wind regime
"JJAS 850-hPa flow is predominantly southwesterly with..."

substrate_terrain | terrain setting
"Median elevation is ..., relief is ..., western boundary is..."

spatial_configuration | upwind land-cover configuration
"Woody cover is concentrated in the prevailing upwind sector..."
```

---

# 31. Enrichment boundary rules

## Wind moisture character

Do not infer:

```text
southwesterly wind = moisture-bearing
```

from direction alone.

To derive moisture character, require supporting fields such as:

- humidity/moisture flux
- trajectory/source-region analysis
- appropriate reanalysis diagnostics

## Seasonal mismatch

Match enrichment temporal scope to the paper context where possible.

Do not compare annual climatological wind against a paper's single wet-season experiment without clearly labeling the difference.

## Reported vs derived disagreement

Preserve both.

No automatic "winner".

---

# 32. Stage 18 — scientific State canonicalization

Claims initially contain open-vocabulary endpoints.

Canonicalization makes graph traversal possible.

Example raw endpoints:

```text
ET
evapotranspiration
land evapotranspiration
surface moisture flux
latent heat flux
```

Not all are identical.

## 32.1 Deterministic normalization

For candidate lookup only:

- lowercase
- Unicode normalize
- trim whitespace
- expand a small curated acronym dictionary
- remove punctuation differences

Do not remove scientifically meaningful words.

## 32.2 Exact alias dictionary

Maintain:

```yaml
evapotranspiration:
  - ET
  - evapotranspiration

planetary boundary layer:
  - PBL
  - planetary boundary layer
  - atmospheric boundary layer
```

Only manually verified aliases should auto-merge initially.

## 32.3 Embedding candidate search

Embed endpoint concept text with Qwen3-Embedding.

Retrieve top `K=5` canonical States.

Embeddings generate candidates; they do not automatically establish identity.

## 32.4 Automatic decision policy

Initial safe policy:

```text
exact normalized alias hit -> merge
otherwise -> do not auto-merge
```

Use an adjudication LLM only for repeated high-value ambiguous concepts as an **offline vocabulary-maintenance step**. It must not silently change per-paper ingest identity; Section 96.16 is normative.

## Prompt: `state_adjudication.txt`

```text
SYSTEM

Decide whether two scientific graph concepts should share the SAME
canonical State concept.

Allowed answers:
- SAME
- RELATED_BUT_DISTINCT
- DIFFERENT
- UNCERTAIN

SAME means the terms can be substituted without changing the scientific
variable/process being represented.

RELATED_BUT_DISTINCT means they are mechanistically connected or often
correlated but should remain separate graph nodes.

Rules:
- Be conservative.
- Do not merge a flux with a state variable.
- Do not merge a mechanism with its outcome.
- Do not merge moisture convergence with moisture recycling.
- Do not merge latent heat flux with evapotranspiration solely because
  they are closely related.
- Use supplied definitions/evidence only.
- Return schema-valid JSON.

USER

Concept A:
{concept_a}

Examples/evidence:
{examples_a}

Concept B:
{concept_b}

Examples/evidence:
{examples_b}
```

The adjudication call is corpus-maintenance, not mandatory per-paper processing.

---

# 33. Stage 19 — embeddings with Qwen3-Embedding

The embedding index is designed for the future query pipeline.

Use one configured model and dimension for the entire active index.

Example default:

```text
EMBED_DIM = 2048
```

Qwen3-Embedding supports Matryoshka/user-defined output dimensions in relevant model sizes. Choose one dimension and keep it fixed across the database.

Normalize embeddings to unit length if cosine similarity will be used.

---

# 34. Facet embeddings

Create two vectors per Facet.

## 34.1 Notion vector

Document text:

```text
{domain} | {notion}
```

Example:

```text
atmosphere | background wind regime
```

Property:

```text
Facet.notion_embedding
```

## 34.2 Content vector

Document text:

```text
Domain: {domain}
Notion: {notion}
Description: {description}
```

Property:

```text
Facet.content_embedding
```

Do not add query instructions to stored document embeddings.

At query time, use Qwen3-Embedding's retrieval instruction on query-side embeddings.

---

# 35. Effective Context construction

Before embedding a Context:

1. obtain ancestors from root → parent;
2. concatenate ancestor local Facets + current local Facets;
3. never mutate stored local Facets;
4. group by domain;
5. construct deterministic retrieval text.

Example:

```text
Context: Amazon wet-season forest control

[climate]
seasonal climate regime:
humid tropical wet-season environment ...

[atmosphere]
background wind regime:
...

[hydrology]
...

[land_surface]
forest state:
continuous evergreen forest ...
```

Store the generated string in extraction artifacts for reproducibility.

Embed it as:

```text
Context.retrieval_embedding
```

---

# 36. Domain balancing for later MaxSim

Do not duplicate a rich domain into dozens of derived facets and let it dominate similarity.

The query pipeline will compute similarity per domain.

Therefore preserve `Facet.domain` exactly and consistently.

Expected later form:

```text
S_context(Q,C)
  = weighted_mean(
      S_spatial_configuration,
      S_land_surface,
      S_hydrology,
      S_atmosphere,
      S_climate,
      S_substrate_terrain
    )
```

Within a domain, MaxSim/UOT operates over the set of Facets.

This is why Facets must remain separate graph nodes.

---

# 37. Claim embeddings

Construct:

```text
FROM: {from.concept} | {from.state}
TO: {to.concept} | {to.state}
RELATION: {relation}
DESCRIPTION: {description}
```

Embed as:

```text
Claim.claim_embedding
```

This supports:

- mechanism retrieval
- claim similarity
- query A→B candidate retrieval
- global synthesis

---

# 38. Transition embeddings

Construct:

```text
FROM CONTEXT: {from label}
TO CONTEXT: {to label}
TRANSITION: {description}
```

Optionally include only a compact land-state/intervention summary.

Embed as:

```text
Transition.transition_embedding
```

This is optional for MVP but inexpensive.

---

# 39. State concept embeddings

Embed:

```text
{canonical concept}
```

Store:

```text
State.concept_embedding
```

Useful for mapping query language and new extraction aliases to canonical mechanism nodes.

---

# 40. Optional SourceBlock embeddings

Persist block embeddings on disk for:

- long-paper evidence bundle construction
- extraction debugging
- future evidence retrieval

They do not need to be indexed in Neo4j initially.

---

# 41. Suggested Qwen query instructions for the future query pipeline

These do not affect indexing, but indexing must be compatible with them.

## Context retrieval

```text
Instruct: Retrieve land-atmosphere study contexts with environmentally
analogous conditions for transferring scientific mechanisms. Match
physical climate, hydrology, atmospheric regime, land surface, spatial
configuration, and terrain rather than geographic name alone.

Query:
{query_context_text}
```

## Facet-notion matching

```text
Instruct: Retrieve context facets describing the same or a closely
related land-atmosphere environmental concept.

Query:
{domain} | {notion}
```

## Claim retrieval

```text
Instruct: Retrieve scientific land-atmosphere findings describing the
same or a closely related mechanism, including equivalent terminology
and directional responses.

Query:
{claim_query}
```

---

# 42. Stage 20 — build `final_paper.json`

This file is the deterministic interchange format between extraction and graph ingestion.

Example top level:

```json
{
  "schema_version": "0.1",
  "pipeline_version": "0.1",
  "paper": {},
  "source_blocks": [],
  "contexts": [],
  "facets": [],
  "transitions": [],
  "claims": [],
  "states": [],
  "evidence_links": [],
  "unresolved_conflicts": [],
  "metadata": {
    "parser": "nemotron-parse-v1.2",
    "extractor_model": "qwen3.6:27b",
    "embedding_model": "qwen3-embedding",
    "prompt_versions": {}
  }
}
```

The graph builder consumes only this file.

The graph builder must contain **no LLM extraction logic**.

---

# 43. LLM extraction envelope

Keep extraction metadata outside the scientific object.

For every raw model call, store:

```json
{
  "call_id": "uuid",
  "paper_id": "P000123",
  "stage": "facet_extraction",
  "model": "qwen3.6:27b",
  "prompt_version": "facet_v1.1",
  "thinking_level": "no",
  "input_block_ids": ["..."],
  "raw_response_path": "...",
  "validated": true,
  "retry_number": 0,
  "created_at": "..."
}
```

This supports prompt benchmarking and selective re-extraction.

---

# 44. Ollama execution policy

Use JSON Schema structured outputs.

Do not rely on "please return valid JSON" alone.

Recommended settings for `qwen3.6:27b` through Ollama:

```text
paper map:
  temperature = 0.1
  thinking = low

section scout:
  temperature = 0
  thinking = no

facet extraction:
  temperature = 0
  thinking = no

claim extraction:
  temperature = 0
  thinking = low

context reconciliation:
  temperature = 0
  thinking = medium

paper consolidation:
  temperature = 0
  thinking = medium

state adjudication:
  temperature = 0
  thinking = low
```

Use only `no`, `low`, or `medium` reasoning for this pipeline. Default downward: use `no` whenever extraction is local and evidence is explicit; use `low` for relationship/structure extraction; reserve `medium` for reconciliation or consolidation across competing evidence.

Do not compensate for an oversized prompt by increasing reasoning. Reduce the evidence bundle or split the call. The configured hard input budget remains authoritative so that reasoning tokens do not unexpectedly consume the model context window.

---

# 45. LLM retry policy

For each structured call:

## Attempt 1

Normal prompt + JSON Schema.

## If JSON validation fails

Retry once with:

```text
Your previous output failed schema validation.

Validation errors:
{errors}

Return a corrected object only.
Do not add any new scientific information.
```

## If referential validation fails

Example:

```text
unknown context_id C8
unknown block_id P17:S9:P2
```

Retry with explicit allowed IDs.

## Maximum

Default total attempts:

```text
3
```

If still invalid:

```text
stage_status = NEEDS_REVIEW
```

Do not silently continue with malformed objects.

---

# 46. Stage 21 — Neo4j graph model

## Node labels

```text
Paper
Context
Facet
Transition
Claim
State
SourceBlock
```

## Relationships

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
(Claim)-[:CONDITIONED_BY]->(Facet)   # zero or more; optional

(Facet)-[:SUPPORTED_BY]->(SourceBlock)
(Context)-[:SUPPORTED_BY]->(SourceBlock)
(Transition)-[:SUPPORTED_BY]->(SourceBlock)
(Claim)-[:SUPPORTED_BY]->(SourceBlock)

(SourceBlock)-[:IN_PAPER]->(Paper)
```

Do not create a direct canonical causal edge such as:

```text
(State)-[:CAUSES]->(State)
```

as the source-of-truth representation.

The `Claim` node is the evidence-bearing edge object.

Graph traversal interprets:

```text
State <-[:FROM]- Claim -[:TO]-> State
```

as one claim-supported mechanism step.

---

# 47. Why Claim is a node

A Claim must retain:

- paper
- context/transition scope
- exact evidence
- relation type
- description
- potentially contradictory sibling evidence

If a direct `CAUSES` relationship were used instead, multiple evidence instances would be harder to keep distinct.

---

# 48. Neo4j constraints

Create uniqueness constraints.

Example Cypher:

```cypher
CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
FOR (n:Paper) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT context_id_unique IF NOT EXISTS
FOR (n:Context) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT facet_id_unique IF NOT EXISTS
FOR (n:Facet) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT transition_id_unique IF NOT EXISTS
FOR (n:Transition) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT claim_id_unique IF NOT EXISTS
FOR (n:Claim) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT state_id_unique IF NOT EXISTS
FOR (n:State) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT sourceblock_id_unique IF NOT EXISTS
FOR (n:SourceBlock) REQUIRE n.id IS UNIQUE;
```

---

# 49. Neo4j full-text indexes

Useful for exact/scientific terminology.

Example intent:

```text
Facet.notion
Facet.description
Claim.description
State.concept
Context.label
```

Implement according to the deployed Neo4j version.

Hybrid retrieval later can union lexical and vector candidates.

---

# 50. Neo4j vector indexes

At minimum create:

```text
Context.retrieval_embedding
Facet.notion_embedding
Facet.content_embedding
Claim.claim_embedding
```

Example modern Cypher shape:

```cypher
CREATE VECTOR INDEX context_embedding_idx IF NOT EXISTS
FOR (n:Context)
ON n.retrieval_embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 2048,
  `vector.similarity_function`: 'cosine'
}};
```

Repeat for each embedding property with the same configured dimension.

If using a Qwen3-Embedding output dimension greater than Neo4j's supported limit, reduce the embedding dimension before indexing. Keep the active corpus dimension fixed.

---

# 51. Stage 22 — transactional graph ingestion

The ingest transaction for one paper must be atomic.

## Algorithm

### A. Start transaction

### B. If paper already exists

Delete paper-owned objects:

- Contexts
- Facets
- Transitions
- Claims
- SourceBlocks

Do **not** delete shared canonical State nodes merely because this paper referenced them.

### C. Upsert Paper

### D. Create SourceBlocks

### E. Create Contexts

### F. Add Context hierarchy

### G. Create Facets

### H. Create Transitions

### I. MERGE canonical States

### J. Create Claims and connect FROM/TO State

For each valid `conditioning_facet_id`, also create:

```text
(Claim)-[:CONDITIONED_BY]->(Facet)
```

Do not create this relationship for inferred or missing Facets.

### K. Add provenance relationships

### L. Verify counts and integrity

### M. Commit

On any error:

```text
ROLLBACK
```

---

# 52. Post-ingestion graph validation

After committing one paper, verify:

```text
all paper contexts reachable from Paper
all facets have one Context
all transitions have FROM and TO
all claims have exactly one scope
all claims have FROM State and TO State
all CONDITIONED_BY links, if present, point to valid Facets reachable from the Claim scope
all reported facets/claims have evidence
all SourceBlocks link to Paper
no Context hierarchy cycle
```

Log graph counts:

```json
{
  "contexts": 4,
  "facets": 27,
  "transitions": 3,
  "claims": 18,
  "states_referenced": 22,
  "source_blocks": 143
}
```

---

# 53. Re-indexing strategy

Do not perform complex graph diffs during early development.

For a new extraction version:

1. preserve old filesystem artifacts;
2. produce new `final_paper.json`;
3. transactionally remove old paper-owned graph objects;
4. ingest new version;
5. keep/reuse canonical States where appropriate.

The active Neo4j graph represents the current pipeline version.

Historical extraction versions remain on disk/object storage.

---

# 54. How indexing supports the query pipeline

The query pipeline is expected to operate roughly as:

```text
user question
  ↓
query parser
  ↓
temporary query Context + optional A/B states
  ↓
optional query-area enrichment
  ↓
Qwen embeddings
  ↓
coarse Context ANN retrieval
  ↓
load candidate Facets
  ↓
domain-wise MaxSim / later UOT
  ↓
context-gated candidate Claims
  ↓
forward / backward / A→B / global graph search
  ↓
top context-coherent paths
  ↓
retrieve SourceBlocks
  ↓
one final evidence-grounded LLM synthesis
```

Therefore indexing must preserve:

- per-Facet vectors
- domains
- Context hierarchy
- Claim scope
- optional Claim `conditioning_facet_ids`
- canonical State endpoints
- provenance

---

# 55. Query modes the graph must support

No extra schema is needed for these.

## Forward

```text
A → ?
```

Example:

```text
deforestation → what?
```

Traverse Claims outward from matching States, gated by applicable Contexts.

## Backward

```text
? → B
```

Example:

```text
what could increase precipitation?
```

Traverse the same graph in reverse.

## A→B

Find candidate paths:

```text
A → ... → B
```

## Global

Ignore query-context applicability filtering or aggregate by Context clusters/regimes.

---

# 56. Context similarity compatibility

Each evidence Claim scopes to a Context or Transition whose effective Context can be reconstructed.

The later query layer computes:

```text
ContextSimilarity(query_context, evidence_context)
```

using Facets.

Do not store one irreversible "context score" during indexing.

The score depends on the future query.

---

# 57. Context inheritance for Transition-scoped Claims

A Transition has:

```text
FROM Context
TO Context
```

For applicability, preserve both.

Do not create one lossy blended Context during indexing.

The query algorithm may later compare:

- common parent context
- baseline/from state
- target/to state

depending on the intervention question.

---

# 58. Boundary case — multiple study areas

Paper:

```text
Amazon experiment
Congo experiment
Southeast Asia experiment
```

Create separate top-level Contexts.

Do not put "tropical forest" into one parent if the paper did not actually use one common experimental context. Cross-paper/global abstraction happens at retrieval time, not by rewriting source structure.

---

# 59. Boundary case — one study area, many scenarios

Prefer:

```text
C1 common Brazil context
├── C1.1 forest
├── C1.2 20% deforestation
├── C1.3 50% deforestation
└── C1.4 grassland
```

rather than four copies of Brazil/climate/wind/soil.

---

# 60. Boundary case — same scenario, multiple seasons

If findings are season-specific and conditions differ materially:

```text
C1 common site
├── C1.1 wet season
└── C1.2 dry season
```

Land-cover state may be another child layer or separate composed context depending on how the paper defines experiments.

Use the minimal hierarchy that accurately scopes findings.

---

# 61. Boundary case — context hierarchy is not perfectly tree-like

The conceptual model may behave like a DAG when reusable dimensions combine.

For the initial implementation, prefer a simple parent hierarchy unless a paper genuinely requires multiple parents.

If multiple-parent inheritance is enabled:

- detect cycles;
- define deterministic ancestor ordering;
- deduplicate inherited Facets by Facet ID;
- never silently resolve conflicting inherited Facets.

---

# 62. Boundary case — review/meta-analysis papers

Do not treat the entire review as one site Context.

If the review reports individual underlying study cases in sufficient detail, extract those as case Contexts and retain the review Paper as provenance.

If the review only synthesizes global qualitative conclusions:

- use global/region-level Contexts as appropriate;
- extract synthesis Claims cautiously;
- do not invent site-level detail.

---

# 63. Boundary case — theoretical/idealized study

Valid Context:

```text
spatial_kind = global / region / unresolved
```

Facets may include:

```text
idealized tropical convective regime
wet-season reference state
analytical theory
```

Do not fabricate coordinates.

---

# 64. Boundary case — methodology

The minimal Context schema is for environmental applicability.

Methodological qualifiers that change the meaning of a result must not be lost.

For v1:

- preserve them in Claim description and scope/evidence;
- optionally represent major model/observation conditions as `other` Facets only when they condition transferability.

Do not let methodology dominate environmental Context similarity unless the query specifically requests methodological matching.

---

# 65. Boundary case — different response metrics

Do not merge:

```text
LST
2-m air temperature
Tmax
Tmin
wet-bulb temperature
precipitation amount
precipitation frequency
precipitation intensity
```

even if a paper informally calls them all "temperature" or "rainfall response".

Measurement identity can reverse interpretation and must remain in Claim endpoints/description.

---

# 66. Boundary case — temporal aggregation

Preserve:

```text
afternoon
daily mean
monthly
wet season
annual
```

in the Claim description and in the scoped Context/Transition where appropriate.

Claims with different aggregation windows are not duplicates.

---

# 67. Boundary case — local vs non-local effects

Do not merge:

```text
local surface response
downwind response
regional remote response
teleconnection
```

when the paper distinguishes them.

Use Claim description and Context/Transition scope to preserve location of the effect.

---

# 68. Boundary case — contradictory Claims

Keep both.

Example:

```text
CL1: soil wetting → convection increase
CL2: soil wetting → convection decrease
```

if supported under different contexts or even conflicting studies.

Do not ask consolidation to decide which is true.

Context-conditioned query retrieval is supposed to expose this heterogeneity.

---

# 69. Boundary case — repeated evidence

If the same scientific point is stated in:

- Results
- Discussion
- Conclusion

create one Claim if meaning/scope are identical and merge all supporting `evidence_block_ids`.

Rule:

> deduplicate knowledge, not evidence.

---

# 70. Boundary case — cited background mechanism

Introduction:

> Smith et al. (2018) showed that ...

Do not automatically treat this as a finding from the current paper.

Options:

- ignore for current-paper Claim extraction;
- later build a citation-aware literature layer if desired.

---

# 71. Boundary case — table-only result

A Claim may be supported by a table if the table is parsed clearly enough.

Evidence should include:

- table block ID
- caption
- relevant nearby explanatory paragraph if available

Do not infer a directional Claim from a malformed table.

Flag for review if table semantics are unclear.

---

# 72. Boundary case — figure-only result

For v1, only extract if:

- caption states the finding; or
- nearby text explicitly describes the figure result.

Do not read numeric values visually from plots unless a dedicated figure-extraction pipeline is added.

---

# 73. Boundary case — supplementary material

If available and parsed:

- treat supplementary document as belonging to the same Paper;
- prefix SourceBlock IDs with supplement marker;
- allow evidence links to supplement blocks.

If unavailable, do not infer missing experimental detail.

---

# 74. Boundary case — missing location

A Context with:

```text
spatial_support = unresolved
```

is fully valid.

Skip enrichment.

It can still be retrieved semantically using climate/land/atmospheric Facets reported by the paper.

---

# 75. Boundary case — broad location name

Example:

```text
Amazon
Mediterranean
Sahel
```

Do not automatically geocode to one point.

Either:

- resolve an appropriate polygon with explicit provenance; or
- retain the named region without enrichment.

---

# 76. Boundary case — numbers inside prose

Do not separately normalize by default.

Keep:

```text
"background winds were typically 4–8 m/s"
```

inside the Facet description.

If later a deterministic numeric parser extracts a useful hint, store it as auxiliary metadata, not as the replacement for the semantic Facet.

---

# 77. Boundary case — wind roses

If text/caption describes the rose:

```text
"dominant southwesterly mode with weaker westerly mode"
```

store that as an atmosphere Facet.

Keep the figure reference.

Future visual embeddings may augment this, but are not required in v1.

---

# 78. Boundary case — observational comparison with no intervention

A paired forest/cropland observation may still have:

```text
Transition = reference Context → comparison Context
```

for organizational purposes.

But Claim relation should be `associative` unless the paper's design supports causal interpretation.

---

# 79. Boundary case — no explicit baseline

Do not fabricate one.

Scope Claims to the relevant Context.

---

# 80. Boundary case — overlapping Context descriptions

If two candidate Contexts appear to be identical except for aliases:

merge during consolidation.

If they differ on a condition that changes findings:

keep separate.

---

# 81. Boundary case — source says "this effect"

Evidence bundle construction should include adjacent blocks and Transition definition so pronouns/cross-references are resolvable.

If still unresolved:

do not guess.

Emit ambiguity.

---

# 82. Failure-state taxonomy

Every stage must return an explicit status.

Suggested:

```text
OK
SKIPPED_NOT_APPLICABLE
NEEDS_REVIEW
FAILED_PARSE
FAILED_SCHEMA
FAILED_REFERENCE_VALIDATION
FAILED_CONTEXT_RECONCILIATION
FAILED_GRAPH_INGEST
```

Never represent failure as an empty valid result.

---

# 83. Pipeline state machine

```text
REGISTERED
  ↓
PARSED
  ↓
CLEANED
  ↓
BLOCKED
  ↓
MAPPED
  ↓
FACETS_EXTRACTED
  ↓
CLAIMS_EXTRACTED
  ↓
RECONCILED
  ↓
CONSOLIDATED
  ↓
VALIDATED
  ↓
[OPTIONALLY_ENRICHED]
  ↓
CANONICALIZED
  ↓
EMBEDDED
  ↓
FINAL_JSON_READY
  ↓
GRAPH_INDEXED
```

Write the current state to `manifest.json`.

---

# 84. Exact end-to-end orchestration pseudocode

```python
def index_pdf(pdf_path):
    paper = register_pdf(pdf_path)

    parsed = nemotron_parse(pdf_path)
    validate_parse(parsed)
    save_raw_parse(parsed)

    cleaned = clean_markdown(parsed)
    save_clean_markdown(cleaned)

    blocks = generate_stable_blocks(cleaned)
    validate_blocks(blocks)
    save_blocks(blocks)

    token_count = count_useful_tokens(blocks)

    if token_count <= CONFIG.whole_paper_threshold_tokens:
        paper_map = llm_map_whole_paper(blocks)
    else:
        section_groups = group_blocks_by_section(blocks)
        scouts = parallel_map(llm_section_scout, section_groups)
        paper_map = llm_consolidate_map(scouts, blocks)

    validate_paper_map(paper_map, blocks)
    registry = assign_permanent_context_ids(paper_map)

    if needs_block_embeddings(token_count, paper_map):
        block_vectors = embed_source_blocks(blocks)

    facet_candidates = []
    for context in registry.contexts:
        bundles = build_context_evidence_bundles(
            context=context,
            registry=registry,
            blocks=blocks,
            block_vectors=block_vectors
        )
        for bundle in bundles:
            result = llm_extract_facets(
                context=context,
                registry=registry,
                evidence=bundle,
                parent_facets=get_parent_facets(context, facet_candidates)
            )
            validate_facet_result(result)
            facet_candidates.extend(result.facets)
            collect_context_hints(result)

    claim_candidates = []
    for transition in registry.transitions:
        bundles = build_transition_evidence_bundles(
            transition=transition,
            registry=registry,
            blocks=blocks,
            block_vectors=block_vectors
        )
        for bundle in bundles:
            result = llm_extract_claims(
                scope=transition,
                registry=registry,
                evidence=bundle
            )
            validate_claim_result(result)
            claim_candidates.extend(result.claims)
            collect_context_hints(result)

    # Optional context-scoped claim extraction for findings not associated
    # with a Transition.
    for context in contexts_with_claim_seeds_but_no_transition(registry):
        bundles = build_context_claim_bundles(...)
        ...

    if collected_context_hints():
        changes = llm_reconcile_context_hints(...)
        apply_registry_changes(changes)

        # Re-run only affected scopes.
        rerun_affected_extractions(...)

    facet_candidates = deterministic_exact_dedupe(facet_candidates)
    claim_candidates = deterministic_exact_dedupe(claim_candidates)

    validate_references(...)

    consolidated = llm_consolidate_paper(
        registry=registry,
        facets=facet_candidates,
        claims=claim_candidates
    )

    validate_consolidated_paper(consolidated, blocks)

    derived_facets = []
    if CONFIG.enrichment_enabled:
        for context in consolidated.contexts:
            if enrichment_is_applicable(context):
                derived_facets.extend(
                    algorithmic_environmental_enrichment(context)
                )

    merged_facets = consolidated.facets + derived_facets

    states = canonicalize_claim_endpoints(
        consolidated.claims,
        alias_registry=load_state_alias_registry()
    )

    embeddings = create_all_embeddings(
        contexts=consolidated.contexts,
        facets=merged_facets,
        claims=consolidated.claims,
        transitions=consolidated.transitions,
        states=states
    )

    final_paper = build_final_paper_json(
        paper=paper,
        source_blocks=blocks,
        contexts=consolidated.contexts,
        facets=merged_facets,
        transitions=consolidated.transitions,
        claims=consolidated.claims,
        states=states,
        embeddings=embeddings
    )

    validate_final_paper(final_paper)
    save_final_paper(final_paper)

    neo4j_transactional_ingest(final_paper)
    validate_graph_for_paper(paper.id)

    mark_manifest_graph_indexed(paper.id)

    return paper.id
```

---

# 85. Parallelization

Safe parallel stages:

```text
section scout calls
Facet extraction across independent Contexts
Claim extraction across independent Transitions
embedding batches
enrichment across Contexts
```

Unsafe without synchronization:

```text
Context Registry mutation
State canonicalization writes
Neo4j paper replacement
```

Use a single authoritative registry update step.

---

# 86. Typical LLM call counts

## Simple paper

```text
1 paper map
1–2 Facet extraction calls
1–3 Claim extraction calls
1 consolidation
≈ 4–7 total
```

## Complex/long paper

```text
N section scouts
1 map consolidation
N_context evidence extraction calls
N_transition claim extraction calls
0–1 context reconciliation
1 paper consolidation
```

Calls increase because the paper has more distinct scientific objects, not because of arbitrary fixed-size chunking.

---

# 87. What the LLM must never do

Keep this list in code comments/tests.

The LLM does **not**:

- parse/geocode coordinates from outside sources;
- query Earth Engine;
- calculate aridity;
- normalize units as a requirement;
- calculate MaxSim;
- calculate UOT;
- score scientific confidence;
- select graph paths;
- perform graph writes;
- decide global truth;
- invent missing intermediate mechanisms;
- overwrite reported context with enrichment;
- silently merge contradictory findings.

---

# 88. What Python/deterministic code does

```text
PDF registration
hashing
Markdown cleaning
stable block IDs
section grouping
token counting
lexical retrieval
vector candidate retrieval
schema validation
referential validation
Context cycle detection
exact deduplication
spatial enrichment
embedding calls
State alias lookup
MaxSim/UOT later
Neo4j graph building
graph integrity validation
```

---

# 89. Extraction QA benchmark

Before indexing hundreds of papers, manually annotate a gold set of approximately 20–50 diverse papers.

Evaluate separately:

```text
Context discovery recall
Context over-splitting rate
Context under-splitting rate
parent/child accuracy
Transition accuracy
Facet precision
Facet recall
Facet domain/notion quality
spatial-configuration Facet accuracy
Claim precision
Claim recall
causal-vs-associative accuracy
Claim scope accuracy
conditioning-Facet precision/recall
evidence-grounding accuracy
```

Do not judge the extraction pipeline only by whether the final prose answer "looks right".

---

# 90. Prompt-version experiments

Record:

```text
model
quantization
context size
prompt version
JSON schema version
temperature
thinking setting
pipeline version
```

Then compare extraction metrics.

Do not change several variables at once when benchmarking.

---

# 91. Later retrieval benchmark

The indexing representation is specifically intended to compare:

```text
whole-context cosine baseline
vs
domain-wise Facet MaxSim
vs
MaxSim + context gating
vs
UOT
vs
UOT + context-coherent path search
```

Therefore do not collapse Facets into one description and discard them after generating a Context embedding.

---

# 92. Minimal example

Source paper structure:

```text
Study area:
Brazilian tropical watershed; wet season; weak easterly background flow.

CTRL:
intact forest.

EXP1:
30% of forest converted to pasture.

Results:
EXP1 reduced ET.
Reduced ET lowered low-level moisture.
Rainfall decreased.
```

## Indexed Contexts

```text
C1
Brazilian tropical wet-season watershed
Facet: climate regime
Facet: background wind regime

C1.1 inherits C1
Facet: intact forest

C1.2 inherits C1
Facet: 30% pasture conversion
```

## Transition

```text
T1
C1.1 → C1.2
```

## Claims

```text
forest cover decrease
    → evapotranspiration decrease

evapotranspiration decrease
    → low-level atmospheric moisture decrease

low-level atmospheric moisture decrease
    → precipitation decrease
```

All Claims scope to `T1`.

## Graph

```text
Paper
 │
 ├── Context C1
 │     ├── Facet climate
 │     ├── Facet wind
 │     ├── C1.1 forest
 │     └── C1.2 pasture
 │
 ├── Transition T1
 │     ├── FROM C1.1
 │     └── TO C1.2
 │
 └── Claims
       │
       ├── State(forest cover ↓)
       │      → Claim
       │      → State(ET ↓)
       │
       ├── State(ET ↓)
       │      → Claim
       │      → State(low-level moisture ↓)
       │
       └── State(low-level moisture ↓)
              → Claim
              → State(precipitation ↓)
```

Every Context/Facet/Transition/Claim links to SourceBlocks.

---

# 93. Final implementation checklist

A paper is ready for the active graph only when all are true:

```text
[ ] original PDF preserved
[ ] Nemotron raw parse preserved
[ ] cleaned Markdown generated
[ ] stable SourceBlocks generated
[ ] paper map generated
[ ] Context hierarchy validated
[ ] Transitions validated
[ ] Facets extracted with evidence
[ ] Claims extracted with evidence
[ ] Claim conditioning Facet references validated
[ ] late Context hints resolved or flagged
[ ] consolidation completed
[ ] no dangling IDs
[ ] no Context inheritance cycle
[ ] reported vs derived provenance preserved
[ ] optional enrichment completed or explicitly skipped
[ ] Claim endpoints canonicalized conservatively
[ ] embeddings generated at configured dimension
[ ] final_paper.json validated
[ ] graph transaction committed
[ ] post-ingest graph integrity passed
[ ] manifest updated
```

---

# 94. Practical MVP order

Do not implement everything at once.

## MVP 1

```text
Nemotron parse
clean Markdown
stable blocks
whole-paper map
Facet extraction
Claim extraction
consolidation
final JSON
Neo4j graph
```

Use only papers under the whole-paper threshold first.

## MVP 2

Add:

```text
long-paper section scouts
evidence-bundle retrieval
Qwen block embeddings
```

## MVP 3

Add:

```text
optional spatial resolution/enrichment
```

## MVP 4

Add:

```text
State canonicalization workflow
Qwen vector indexes
hybrid lexical/vector retrieval
```

## MVP 5

Benchmark:

```text
MaxSim
UOT
context-aware mechanism paths
```

---

# 95. External implementation references

These are implementation references, not scientific sources.

- NVIDIA Nemotron-Parse model:
  https://build.nvidia.com/nvidia/nemotron-parse

- NVIDIA Nemotron-Parse v1.2 API documentation:
  https://docs.nvidia.com/nim/vision-language-models/1.7.0/examples/nemotron-parse/api.html

- Ollama structured outputs:
  https://docs.ollama.com/capabilities/structured-outputs

- Ollama generate API (`format` supports JSON Schema):
  https://docs.ollama.com/api/generate

- Ollama `qwen3.6:27b`:
  https://ollama.com/library/qwen3.6:27b

- Qwen3-Embedding-8B:
  https://huggingface.co/Qwen/Qwen3-Embedding-8B

- Qwen3-Embedding-4B:
  https://huggingface.co/Qwen/Qwen3-Embedding-4B

- Neo4j vector indexes:
  https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/

- Neo4j VECTOR type:
  https://neo4j.com/docs/cypher-manual/current/values-and-types/vector/

---

# 96. Normative implementation-resolution algorithms

This section is **normative**. It resolves shorthand such as “select”, “merge”, “reconcile”, “retrieve relevant blocks”, and “prefer” used earlier in this document. If an earlier stage description is less specific than this section, implement the algorithm here.

The implementation principle is:

> deterministic code narrows the problem; Qwen performs only bounded semantic classification/extraction; deterministic code validates and applies the result.

Do not let the coding agent invent an alternative algorithm unless a configuration/version change explicitly replaces the rule below.

---

## 96.1 Common normalization helpers

Use these helpers everywhere IDs or duplicate keys are compared.

```python
import re, unicodedata

def normalize_text_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    s = re.sub(r"[^\w%+./-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
```

For scientific concepts, additionally expand **only** entries in the curated acronym/alias registry before computing a lookup key. Never stem scientific terms and never delete modifiers such as `surface`, `maximum`, `low-level`, `convective`, `moisture`, or `flux`.

Evidence arrays are canonicalized as sorted unique SourceBlock IDs in paper order.

---

## 96.2 Stable SourceBlock splitting

Set:

```yaml
blocks:
  max_block_tokens: 1500
  target_split_tokens: 1100
```

Algorithm:

1. Parse cleaned Markdown into atomic structural elements: heading, paragraph, list group, table, caption, display equation.
2. One structural element becomes one SourceBlock if token count `<= max_block_tokens`.
3. For an oversized paragraph/list group:
   - sentence-split with the configured sentence tokenizer;
   - greedily append sentences until adding the next sentence would exceed `target_split_tokens`;
   - if one sentence itself exceeds `max_block_tokens`, split it at semicolon/comma boundaries; if still too long, hard-split at the nearest whitespace before `max_block_tokens` and flag `oversize_hard_split=true`.
4. For an oversized table:
   - retain the caption as its own block;
   - repeat the table header in every split;
   - greedily add contiguous rows until the next row would exceed `target_split_tokens`;
   - never reorder rows.
5. A displayed equation and the immediately following explanatory paragraph remain separate SourceBlocks, but neighbor expansion later ensures they can be supplied together.
6. Stable suffixes `:A`, `:B`, ... follow original order.

No semantic LLM call is used here.

---

## 96.3 Long-paper section grouping

The scout grouping algorithm is deterministic.

```yaml
section_scout:
  target_tokens: 6500
  min_tokens: 3500
  max_tokens: 8000
```

1. Start with blocks grouped by level-1/level-2 heading path.
2. If a group is `<= 8000` tokens, keep it intact.
3. If larger, split first on deeper subheadings.
4. If a resulting subgroup is still too large, greedily pack consecutive SourceBlocks up to `target_tokens` without exceeding `max_tokens`.
5. If a group smaller than `min_tokens` has an immediately adjacent group under the same parent heading and their combined size is `<= max_tokens`, merge them.
6. Never move blocks across original order.

Every scout input carries its full heading path and exact SourceBlock IDs.

---

## 96.4 Selecting original blocks for scout consolidation

`map_consolidation.txt` receives a compact structural evidence packet. Do not rescan the paper using broad words such as `case`, `site`, or `domain`; those words occur too widely to be useful selectors.

Construct candidates in this priority order:

1. the first valid SourceBlock cited by every scout Context, comparison, and location mention;
2. title and abstract blocks;
3. additional SourceBlocks cited by those mentions;
4. scout `facet_seed_block_ids`;
5. scout `claim_seed_block_ids`.

Deduplicate candidates by SourceBlock ID. Greedily add them in priority order without exceeding `paper_mapping.map_consolidation_source_budget_tokens`, then restore original paper order for the LLM request. Do not add automatic neighbors or global method-keyword matches. The scout description remains available when a lower-priority supporting block does not fit.

Save `map_input_report.json` containing the source budget, estimated selected tokens, selected IDs, and dropped IDs grouped by priority reason.

---

## 96.5 Exact within-paper lexical retrieval

Use BM25 over SourceBlocks, not ad-hoc substring counts.

Recommended implementation: `rank_bm25` or an equivalent deterministic BM25 implementation with:

```text
k1 = 1.5
b  = 0.75
```

Tokenization for BM25:

```text
NFKC → lowercase → whitespace/punctuation tokenization
```

Do not stem. Retain scientific abbreviations and numbers.

Each retrieval request is a list of query strings. Score a block by the **maximum BM25 score across query strings**. Retrieve `lexical_top_k` unique blocks after excluding bibliography.

Exact alias occurrences receive an independent boolean `alias_hit=true`; do not rely only on BM25 for aliases.

---

## 96.6 Exact semantic block retrieval

If block embeddings are enabled:

1. normalize all block embeddings to unit length;
2. embed each deterministic retrieval query string;
3. compute cosine similarity by matrix multiplication;
4. for each block, retain its maximum cosine across query strings;
5. take `semantic_top_k` unique blocks.

Do not apply a semantic threshold in MVP. The semantic result is candidate generation only.

If block embeddings are disabled, semantic candidate generation is skipped; the remainder of the algorithm is unchanged.

---

## 96.7 Context evidence-bundle construction

For target Context `C`, build candidates with the following exact procedure.

### Query strings

Create:

```python
queries = [C.label] + C.aliases
queries += [
    "study area location climate season meteorology",
    "wind atmospheric circulation humidity boundary layer",
    "land cover land use vegetation management",
    "hydrology soil moisture",
    "terrain topography elevation",
    "spatial configuration patch heterogeneity edge"
]
```

Also add each parent alias prefixed with `background context` and each child alias prefixed with `scenario` only to improve recall; these do not change ownership of extracted Facets.

### Candidate union

Include:

```text
A. map facet_seed_block_ids
B. exact target alias hits
C. BM25 top lexical_top_k
D. cosine top semantic_top_k, if available
E. ±neighbor_blocks_each_side around A–D
```

Exclude bibliography before scoring.

### Priority tuple

Do **not** sum arbitrary point scores. Sort by this lexicographic priority tuple:

```text
(
  is_map_seed,                 # True first
  is_exact_target_alias_hit,   # True first
  section_priority,            # Methods/Study Area=3, Results=2, Discussion=1, other=0
  semantic_rank_score,         # reciprocal rank: 1/rank, else 0
  lexical_rank_score,          # reciprocal rank: 1/rank, else 0
  is_neighbor                  # direct hit before neighbor
)
```

Within ties, use original SourceBlock order.

### Adjacency preservation

A selected direct block defines an evidence group consisting of itself plus selected contiguous neighbors. When trimming, keep/drop a group as a unit unless the direct block is a mandatory map seed. Mandatory seeds are never dropped.

### Budget

Greedily retain groups in priority order until adding a group would exceed `evidence_input_budget_tokens`. Restore original paper order before the LLM call.

If mandatory seeds alone exceed the budget, split the bundle by the three domain groups already defined in Stage 17.4 and repeat the same candidate construction per group.

---

## 96.8 Transition/Claim evidence-bundle construction

Use the same BM25/cosine/neighbor machinery as Section 96.7, with these differences.

Mandatory blocks:

```text
Transition evidence_block_ids
claim_seed_block_ids
```

Section priority:

```text
Results/Analysis = 4
Discussion/Mechanism/Sensitivity = 3
Conclusions = 2
Methods/Experimental Design = 1
other = 0
```

Retrieval query strings are generated from:

```text
transition label + aliases
from-context aliases
to-context aliases
endpoint/outcome keyword families from Stage 19.2
```

If the bundle exceeds budget, split by outcome family. A deterministic keyword classifier assigns a block to every matching family; blocks matching no family go to `other`. Transition-definition blocks are copied into every sub-bundle. A Claim extracted from a sub-bundle still uses the same `scope_id`.

---

## 96.9 Facet ownership and conditioning rules

The LLM may semantically extract a Facet, but deterministic validation decides whether it can be attached.

A returned Facet is accepted only if:

1. `context_id == target_context_id`;
2. all evidence IDs are in the supplied bundle;
3. `domain` is allowed;
4. `notion` and `description` are non-empty;
5. it does not exactly duplicate a parent Facet after `normalize_text_key` on `(domain, notion, description)`.

If condition 5 fails, discard the child duplicate and union its evidence into the parent **only if the cited evidence explicitly applies to the parent/common context**; otherwise retain it locally and raise `PARENT_DUPLICATE_AMBIGUOUS`.

For `Claim.conditioning_facet_ids`, accept only Facet IDs reachable from the Claim scope:

- Context-scoped Claim: local + inherited Facets of that Context;
- Transition-scoped Claim: Facets from FROM, TO, and their common ancestors.

A conditioning link is semantically appropriate only when supplied evidence explicitly indicates dependency/relevance using language equivalent to `depends on`, `under`, `when`, `only if`, `stronger/weaker in`, `because of the background`, or when the Facet is an explicit experimental condition necessary to interpret the result. General descriptive Context Facets are not automatically conditioning Facets.

Invalid conditioning IDs are removed and logged; they do not invalidate the Claim itself.

---

## 96.10 Exact duplicate removal before semantic consolidation

### Facet exact key

```text
(context_id,
 normalize(domain),
 normalize(notion),
 normalize(description))
```

For identical keys, keep the earliest candidate object and union evidence IDs.

### Claim exact key

```text
(scope_id,
 normalize(from.concept), normalize(from.state),
 relation,
 normalize(to.concept), normalize(to.state),
 normalize(description))
```

For identical keys, keep the earliest candidate, union evidence IDs and conditioning Facet IDs.

### Transition exact key

```text
(from_context_id, to_context_id, normalize(description))
```

Union evidence/aliases for identical keys.

No embedding is used in this exact pass.

---

## 96.11 Semantic near-duplicate candidate generation

The consolidation LLM must not compare every object to every other object.

### Facets

Only generate a pair if:

```text
same context_id
AND same domain
AND (
  normalized notion equal
  OR notion cosine >= 0.82
  OR content cosine >= 0.88
)
```

These thresholds are **candidate-generation thresholds**, not scientific similarity thresholds.

### Claims

Only generate a pair if:

```text
same scope_id
AND same relation
AND from-concept cosine >= 0.88
AND to-concept cosine >= 0.88
AND state strings are exactly equal after curated state-direction normalization
```

Do not generate duplicate candidates across different response metrics or different scope IDs.

### Contexts

No Context is auto-merged by embedding. Context candidate pairs come only from:

- shared exact alias;
- identical resolved geometry/spatial support plus near-identical scenario label;
- an explicit `unmapped_context_hint` collision;
- the paper-map/consolidation LLM proposing the pair.

This deliberately under-merges Contexts.

---

## 96.12 Bounded semantic consolidation protocol

For each candidate pair/cluster from Section 96.11, Qwen returns only an adjudication label and canonical candidate IDs; it does not create new scientific objects.

Allowed decisions:

```text
SAME
DISTINCT
PARENT_CHILD   # Contexts only
UNCERTAIN
```

Deterministic application:

- `SAME`: merge.
- `DISTINCT`: keep both.
- `PARENT_CHILD`: apply only if both Contexts are already present and the proposed relation does not create a cycle; otherwise `UNCERTAIN`.
- `UNCERTAIN`: keep both and add a review warning.

When merging Facets/Claims:

1. canonical object = candidate with most unique evidence blocks;
2. tie → candidate with longer description;
3. tie → earliest candidate creation order;
4. union evidence and conditioning IDs;
5. **do not synthesize a new description**; retain the canonical candidate's description.

When merging Contexts:

1. canonical Context = earlier permanent ID;
2. union aliases and evidence;
3. redirect child/Transition/Facet/Claim references;
4. if both have conflicting non-null SpatialSupport geometries/resolutions, abort merge as `UNCERTAIN`;
5. run cycle/reference validation immediately.

The existing `paper_consolidation.txt` call may batch these decisions, but its output must be reducible to these exact operations.

---

## 96.13 Late Context-hint reconciliation application

For each `unmapped_context_hint`, first deterministically gather candidate existing Contexts sharing any alias token or cited SourceBlock neighborhood. Qwen then returns one of the five actions already specified.

Application is exact:

- `ATTACH_TO_EXISTING_CONTEXT`: reassign only the objects named in the reconciliation output.
- `ADD_CHILD_CONTEXT`: create one new Context whose parent is the specified existing Context.
- `ADD_INDEPENDENT_CONTEXT`: create one root Context.
- `IGNORE_AS_NOT_A_CONTEXT`: discard the hint only; do not delete already valid objects.
- `UNRESOLVED`: create no Context; affected candidate objects are excluded from final graph and stored in `unresolved_extractions.json`.

If a new Context is created, rerun Facet/Claim extraction only for the cited hint blocks ±1 neighbors plus map/scenario definition blocks; do not rescan the full paper.

Maximum reconciliation rounds per paper: `2`. If new hints remain after round 2, mark `NEEDS_REVIEW` and continue indexing only objects with valid scopes.

---

## 96.14 Named-place resolution for enrichment

Spatial resolution is implemented through a versioned resolver interface, not the generative LLM.

Resolution precedence:

```text
explicit geometry in paper metadata/application
> known registry ID
> exact gazetteer polygon match
> exact gazetteer point match
> unresolved
```

For a gazetteer name with multiple candidates, resolve automatically only when exactly one candidate matches all explicit administrative/country qualifiers from the paper. Otherwise set `resolution="unresolved"` and skip local enrichment.

Never choose the highest-population or nearest centroid candidate without explicit disambiguating evidence.

---

## 96.15 Deterministic environmental enrichment algorithms

All enrichment functions are shared with the query pipeline. Each derived Facet records dataset name/version, temporal window, geometry hash, and algorithm version.

### 96.15.1 Polygon raster aggregation

For categorical rasters, compute area-weighted class fractions using pixel-polygon intersection area. For continuous rasters, compute area-weighted mean, median, p10, and p90. For a point, use the containing pixel plus dataset native-resolution metadata.

Pixels with nodata are excluded. If valid coverage `< 0.8` of polygon area, do not emit a categorical derived conclusion; emit `ENRICHMENT_LOW_COVERAGE`.

### 96.15.2 Climate regime

Using the configured Köppen–Geiger raster:

1. compute area fraction by class;
2. sort descending;
3. if top class fraction `>= 0.60`, describe it as dominant and report its fraction;
4. otherwise describe the polygon as mixed and report the top classes until cumulative area `>= 0.80` or three classes are listed.

No LLM is needed to classify the raster.

### 96.15.3 Aridity/hydroclimate

For reference period configured in `pipeline.yaml`:

```text
AI = mean_annual_precipitation / mean_annual_PET
```

Compute precipitation and PET as area-weighted annual climatological means before taking the ratio. Do not average pixelwise ratios.

Default labels:

```text
AI < 0.05          hyper-arid
0.05 <= AI < 0.20  arid
0.20 <= AI < 0.50  semi-arid
0.50 <= AI < 0.65  dry sub-humid
AI >= 0.65         humid
```

Store the numeric AI and label in the description. Thresholds are versioned configuration.

### 96.15.4 Seasonal wind regime

Use configured reanalysis `u` and `v` at the configured pressure level/time window. For each time step, spatially average `u` and `v` over the geometry first. Then for each season/window:

```python
u_bar = mean(u_t)
v_bar = mean(v_t)
mean_speed = mean(sqrt(u_t**2 + v_t**2))
vector_speed = sqrt(u_bar**2 + v_bar**2)
directional_persistence = vector_speed / max(mean_speed, eps)
wind_to_deg = (degrees(atan2(u_bar, v_bar)) + 360) % 360
wind_from_deg = (wind_to_deg + 180) % 360
```

Convert degrees to 8-point compass labels only for description rendering. Preserve numeric direction internally.

If `directional_persistence < 0.55`, describe the flow as directionally variable and do not emit a single fixed-direction spatial_configuration Facet.

Do not call the flow `moisture-bearing` from direction alone. That phrase requires configured humidity/moisture-flux diagnostics.

### 96.15.5 Terrain

From the configured DEM:

```text
median elevation
p10/p90 elevation
relief = p90 - p10
median slope from 3x3 Horn gradient
```

Describe terrain with these statistics. Do not infer windward/leeward without the terrain-flow algorithm in the query pipeline.

### 96.15.6 Land-cover composition/configuration

From the configured categorical LULC raster:

1. area-weighted fraction by class;
2. retain classes with fraction `>= 0.05` plus the largest class;
3. for each retained class, compute 8-neighbor connected components at native or explicitly configured analysis resolution;
4. report median component area and largest component area;
5. compute edge density as total class-boundary length divided by polygon area.

These metrics may be summarized into one or a few descriptive `land_surface` / `spatial_configuration` Facets. They are auxiliary calculations, not new schema columns.

---

## 96.16 State canonicalization and vocabulary normalization

The canonicalization decision tree is exact:

```python
raw = normalize_concept(raw_concept)
if raw in verified_alias_to_canonical:
    canonical_concept = verified_alias_to_canonical[raw]
else:
    canonical_concept = create_new_canonical_concept(raw_concept)
```

Embedding top-K is used only to populate a maintenance queue for possible future alias addition. It **does not alter the per-paper ingest result** unless an alias has already been manually/explicitly approved in `state_aliases.yaml`.

State-direction normalization uses a separate curated registry, for example:

```yaml
increase: [increase, increased, higher, rise, rising, enhancement]
decrease: [decrease, decreased, lower, decline, reduction]
no_detectable_change: [no detectable change, no significant change, null effect]
```

If a state phrase is not in the registry, retain its normalized open text. Do not force it into increase/decrease.

This means graph identity is deterministic and reproducible across runs.

---

## 96.17 Final JSON ordering

Before hashing/saving `final_paper.json`, sort deterministically:

```text
Contexts       by context_id
Facets         by facet_id
Transitions    by transition_id
Claims         by claim_id
States         by state_id
SourceBlocks   by order
all ID arrays  by canonical paper order where applicable
```

Serialize UTF-8 JSON with sorted object keys for manifests/hashes, while a pretty-printed copy may be written for inspection.

---

## 96.18 Neo4j re-index transaction details

Re-indexing one paper must not leave dangling shared-State edges.

Transaction order:

1. match existing Paper by `paper_id`;
2. collect IDs of paper-owned Claims/Facets/Transitions/Contexts/SourceBlocks;
3. delete relationships from those nodes, then delete the paper-owned nodes;
4. keep shared `State` nodes;
5. upsert Paper;
6. create SourceBlocks, Contexts, hierarchy, Facets, Transitions;
7. `MERGE` State by stable `state_id`;
8. create Claims and all scope/FROM/TO/CONDITIONED_BY/SUPPORTED_BY relations;
9. run in-transaction count/reference assertions;
10. commit;
11. after commit, optionally delete orphan State nodes only in a separate maintenance job, never inside a paper re-index transaction.

Any assertion failure rolls back the whole paper transaction.

---

## 96.19 LLM input-budget enforcement

For every Qwen call:

```python
estimated_input = tokens(system_prompt + schema + payload)
if estimated_input > hard_llm_input_budget_tokens:
    shrink_or_split_payload()
    recompute()
if still > hard_llm_input_budget_tokens:
    fail_stage("FAILED_INPUT_BUDGET")
```

Never switch `thinking` upward to compensate for insufficient evidence or an oversized prompt.

Reasoning levels remain:

```text
no      extraction/routing with local evidence
low     relation extraction / state adjudication
medium  paper-wide reconciliation/consolidation only
```

No indexing stage may use `high` reasoning.

---

## 96.20 Deterministic retry and abstention

For structured-output LLM calls:

1. Attempt 1 with configured prompt/model.
2. If JSON/schema invalid, retry once with the validation error plus the same evidence; do not add scientific hints.
3. If referential IDs are invalid, retry once with the valid ID set and ask only for reference repair.
4. After configured maximum attempts, mark the stage `NEEDS_REVIEW` or `FAILED_SCHEMA`; never accept partially parsed free text.

For semantic decisions (`SAME`, Context reconciliation, causality), `UNCERTAIN` is a valid successful output. The pipeline must prefer abstention to forced resolution.

---

## 96.21 Implementation-ready acceptance test

The indexing implementation is considered conformant only if a replay with identical:

```text
PDF bytes
parser version
pipeline config
prompt versions
model/version identifiers
alias registries
enrichment dataset versions
```

produces the same structural IDs, same deterministic candidate sets, same validation decisions, and semantically equivalent LLM JSON. Exact byte identity of LLM descriptions is not required, but any difference in graph topology/object counts must be surfaced by the regression test.

# 97. Corpus-derived implementation rules and stress tests

This section was added after testing the specification against the project paper corpus. It is normative where it tightens an earlier rule.

## 97.1 Exact Context-vs-Facet split rule

A condition becomes a separate child `Context` only when at least one of the following is true:

1. the paper explicitly defines it as a separate experiment, control, scenario, site, season, time-of-day stratum, or atmospheric regime **and reports one or more findings separately for it**;
2. the sign/category of a reported effect differs across the condition (`increase` vs `decrease`, `effect` vs `no detectable change`, daytime vs nighttime reversal, etc.);
3. a Claim would be misleading if scoped to the parent without naming the condition;
4. the condition is a FROM or TO state in an explicit comparison/Transition.

Otherwise keep the information as a Facet description on the existing Context.

Examples from the benchmark corpus:

- Froidevaux: background-wind and zero/weak-wind experiments can be separate child Contexts because the soil-moisture/precipitation feedback changes sign.
- Klein: daytime and nighttime may be separate child Contexts when Claims have opposite rainfall responses.
- Barron-Gafford: nighttime warming is a Claim qualifier; create a separate nighttime Context only if the paper reports a materially different daytime/nighttime response that is used by multiple Claims.
- A single statement such as “the wet season is JJAS” remains a Facet description unless findings are explicitly stratified by season.

The mapping LLM performs the semantic classification, but it must return for every proposed child Context:

```json
{
  "split_reason": "separate_reported_finding | sign_or_null_reversal | misleading_parent_scope | explicit_transition_state",
  "supporting_block_ids": ["..."]
}
```

Deterministic validation rejects a child Context whose `split_reason` is absent or whose cited blocks do not exist. It does not attempt to re-decide the scientific semantics.

## 97.2 Claim conditioning-Facet resolution algorithm

`conditioning_facet_ids` must not depend on the extraction model remembering arbitrary Facet IDs.

For each extracted Claim:

1. gather all reachable effective Facets allowed by Section 96.9;
2. candidate-generate Facets whose evidence blocks are either:
   - in the Claim evidence set; or
   - within ±2 SourceBlocks of Claim evidence; or
   - in the experimental/method blocks defining the Claim scope;
3. add semantic candidates when cosine between `claim.description` and Facet content embedding is `>= 0.45`; this threshold is recall-oriented candidate generation only;
4. send the Claim plus **only these candidate Facets** to Qwen with `thinking=no` or `low` and require one label per candidate:

```text
CONDITIONING
BACKGROUND_ONLY
UNRELATED
UNCERTAIN
```

5. accept only `CONDITIONING`; `UNCERTAIN` is not linked;
6. apply the reachability/evidence rules in Section 96.9;
7. store the adjudication and prompt version in the paper audit artifact.

A Facet is `CONDITIONING` when changing/violating that Facet would plausibly change the interpretation, sign, strength, location, or transferability of the Claim **according to the supplied paper evidence**. Mere co-location in the same Context is `BACKGROUND_ONLY`.

Use this exact adjudication prompt with `thinking=no`:

```text
SYSTEM
You decide whether an existing Context Facet specifically conditions the
interpretation or transferability of one already-extracted Claim.
Use only the supplied Claim, Facet, and evidence passages.
Return exactly one label: CONDITIONING, BACKGROUND_ONLY, UNRELATED, UNCERTAIN.
CONDITIONING requires evidence that the effect depends on, changes under,
is stronger/weaker under, is located/oriented by, or is experimentally
defined by the Facet. Mere coexistence in the study Context is BACKGROUND_ONLY.
When uncertain, return UNCERTAIN.

USER
Claim: {claim}
Candidate Facet: {facet}
Claim evidence: {claim_evidence}
Facet evidence: {facet_evidence}
```

This bounded pass is mandatory when one or more candidate Facets are generated by steps 2–3 and the Claim is used for spatial transfer or the paper reports conditional/reversing effects. Otherwise it may be skipped and the primary extractor's validated conditioning IDs are retained.

## 97.3 Spatial evidence preservation rule

For any reported finding involving `upwind`, `downwind`, `upstream/downstream in the atmospheric sense`, `windward`, `leeward`, `edge`, `interior`, `patch`, `gradient`, `distance`, `annulus`, `source region`, `sink region`, `precipitationshed`, or `teleconnection`:

1. preserve the relation verbatim/paraphrastically in the Claim `description`;
2. extract at least one `spatial_configuration` Facet when the relation describes the supporting Context rather than merely the outcome;
3. preserve explicit numeric scales in the Facet/Claim description with units;
4. preserve the relevant atmospheric wind/moisture-transport Facet separately when reported;
5. never collapse a relative spatial relation into only a generic endpoint such as `precipitation | increase`.

Example:

```text
FROM: convective cell propagation | downwind
TO: precipitation over wet patch | increase
Claim description: Cells initiated over dry patches propagate downwind into wet patches, where higher CAPE strengthens convection and precipitation.
```

The exact endpoints may differ with paper wording; the required invariant is that the directional mechanism survives in the Claim description and provenance.

## 97.4 Own finding vs cited-background test

The paper tests showed this is essential for review papers and introductions.

A candidate Claim is tagged internally during extraction as one of:

```text
OWN_RESULT
AUTHORS_INTERPRETATION_OF_OWN_RESULT
CITED_BACKGROUND
HYPOTHESIS_OR_PROPOSAL
```

Only the first two are ingested as ordinary evidence-bearing Claims.

`CITED_BACKGROUND` is not ingested as this paper's Claim. The cited paper can contribute the Claim only when that cited source itself is indexed.

`HYPOTHESIS_OR_PROPOSAL` may be stored only when the project later introduces an explicit hypothesis object; under the current schema it is omitted from the scientific Claim graph.

The Claim extractor must return `evidence_role` for each candidate; deterministic validation accepts only the first two values. This is an extraction-control field and does not need to become a Neo4j property unless useful for audit.

This prevents, for example, Thiery 2020's introduction citations about irrigation changing remote precipitation from becoming Thiery 2020 findings unless the study itself demonstrates that result.

## 97.5 Quantitative/non-monotonic effect rule

When the paper reports a non-monotonic, thresholded, or scale-specific result, do not reduce it to a generic monotonic Claim.

Examples:

- Rieck: intermediate patch size can accelerate shallow-to-deep transition; “larger patches always improve convection” would be incorrect.
- Patton: strongest organized motions occur for a range of heterogeneity scale relative to boundary-layer height, not monotonically with patch size.
- Cohn: non-local warming is evaluated in explicit distance annuli.

Extraction behavior:

1. keep a compact endpoint state suitable for graph identity;
2. put the numeric range/optimum/shape in `description`;
3. if two ranges have qualitatively different outcomes, extract separate Claims;
4. if a continuous relationship is reported without a categorical breakpoint, one Claim with the relationship in the description is preferred over inventing bins.

## 97.6 State-direction normalization additions

The curated state-direction registry should include morphology/synonyms for common land-atmosphere result forms, while preserving meaning classes separately:

```yaml
increase: [increase, increased, increasing, higher, rise, rising, enhancement, enhanced, warmer, warming]
decrease: [decrease, decreased, decreasing, lower, decline, declining, reduction, reduced, cooler, cooling]
strengthen: [strengthen, strengthened, stronger, intensify, intensified]
weaken: [weaken, weakened, weaker, diminish, diminished]
earlier: [earlier, advance, advanced]
later: [later, delay, delayed]
more_frequent: [more frequent, increased frequency, more likely, higher probability]
less_frequent: [less frequent, reduced frequency, less likely, lower probability]
no_detectable_change: [no detectable change, no significant change, insignificant effect, null effect]
```

Do **not** merge these classes with each other. `increase` and `strengthen`, for example, are not universal synonyms. The registry normalizes surface forms only within a semantic state class.

## 97.7 Corpus stress-test matrix

The following tests were derived from the supplied papers and should become extraction regression tests. They are **expected behavior**, not hand-authored final graph truth; exact Claim decomposition may vary if evidence supports an equivalent structure.

| Paper/case | What the implementation must preserve | Main failure this catches |
|---|---|---|
| Shukla et al., Amazon deforestation | forest→degraded-pasture Transition; warming, ET decrease, precipitation decrease, moisture-convergence decrease; remote circulation statements kept uncertain when authors say attribution is unclear | invented universal mechanism; cited/speculative remote effect promoted to fact |
| Duveiller et al., afforestation/clouds | observational/global Context; increase in low-level cloud cover in many sampled areas; forest-type and geographic/seasonal dependence; mechanistic discussion separated from directly observed association | over-generalizing a global average; causalizing observational evidence |
| Thiery et al., irrigation/hot extremes | irrigation expansion→hot-extreme cooling/reduced likelihood; stronger South Asia/irrigation-hotspot applicability; remote precipitation claims in introduction not treated as own findings | cited-background leakage |
| Barron-Gafford et al., PV heat island | PV-vs-wildland comparison; nighttime 3–4 °C warming retained in description; time-of-day dependence preserved | State fragmentation into `temperature increase at night by 3–4°C`; loss of timing qualifier |
| Taylor et al., Sahel soil-moisture patterns | 10–40 km heterogeneity/gradient; storm-initiation preference; observational relation; spatial scale retained | flattening patch geometry to generic soil moisture |
| Froidevaux et al., background wind | dry-patch initiation + downwind propagation + strengthening over wet patch; background wind changes feedback sign; wind Facet is conditioning | missing conditional sign reversal; treating wind as irrelevant background |
| Rieck et al., patch size | 12.8 km/intermediate-patch accelerated transition and non-monotonic scale behavior | false monotonic “bigger patch is better” Claim |
| Cohn et al., forest-loss distance decay | local plus non-local maximum-temperature response; 1–2, 2–4, 4–10, 10–50 km annuli retained | losing distance structure or inventing exact transfer beyond studied scales |
| Keys et al., precipitationsheds | upwind evaporation source→downwind precipitation dependency; precipitationshed boundary is threshold/time dependent, not a fixed geometric upwind sector | treating precipitationshed as ordinary local wind sector |
| Thiery et al., African Great Lakes | precipitation effect mainly over lake surface but temperature effect has downwind reach; outcome-specific spatial footprints remain separate Claims | assigning one spatial footprint to all outcomes |
| Rabin et al., landscape variability/clouds | cloud preference can differ under relatively moist vs dry atmospheric profiles; downwind bands and weak synoptic forcing preserved | transferring sign without atmospheric conditioning |
| Klein et al., West African vegetation | daytime and nighttime rainfall response can reverse; horizontal-circulation mechanism and atmospheric coincidence condition preserved | averaging opposite diurnal effects into one Claim |

## 97.8 Extraction regression-test procedure

For each benchmark paper:

1. manually maintain a small `expected_invariants.yaml`, not a full gold graph;
2. run the complete indexing pipeline from cleaned Markdown;
3. assert structural invariants, e.g. required Transition exists, at least one Claim mentions the expected outcome, required spatial scale occurs in some provenance-backed description, forbidden cited-background Claim is absent;
4. inspect Claim/Facet evidence IDs and require every expected invariant to resolve to at least one SourceBlock;
5. run a second time with identical model/config versions and compare normalized object keys plus provenance;
6. record extraction recall/error types, not exact object-count equality.

Example invariant:

```yaml
paper: froidevaux2014
must_have:
  - facet_domain: atmosphere
    description_contains_any: [background wind, midtropospheric flow]
  - claim_description_contains_all: [propagate, wet]
  - claim_description_contains_any: [downwind, downstream]
  - spatial_facet_contains_any: [dry patch, wet patch, gradient]
forbid:
  - universal_claim: "wet soil always increases precipitation"
```

The benchmark should tolerate scientifically equivalent wording while catching schema/algorithm failures.

## 97.9 Complete-setting tree rule

The paper map is a compact tree or directed acyclic hierarchy of **complete study settings**. For any Context `C`:

```text
Effective(C) = Facets(C) union Facets(all ancestors of C)
```

`Effective(C)` must contain the combination of conditions needed to understand where findings scoped to `C` apply. Conditions that vary independently in the experiment must not be emitted only as disconnected sibling Contexts when the paper reports results for their combinations.

For factorial, sensitivity, treatment, seasonal, regional, or model-comparison studies:

1. put paper-wide conditions in a root;
2. put conditions shared by several reported settings in intermediate parents;
3. preserve every separately reported experiment, control, scenario, site, season, or case as a leaf or as an exact paper-local alias of the corresponding complete setting;
4. place each differing experimental value on the branch where it applies;
5. construct Transitions between complete endpoints that hold other relevant conditions fixed when the paper does so.

"Minimum Context hierarchy" means minimum repetition through inheritance. It does not permit dropping the identity of a separately reported setting.

Outcome-defined groups become Contexts only when the paper analyzes the group as a setting for multiple findings. Otherwise the outcome is represented by Claims supported by result SourceBlocks.

Mapping prompts must state this rule in ordinary language and must not contain benchmark-paper names or identifiers. Prompt evaluation uses a small multi-structure corpus, but corpus examples are not inserted into production prompts.

For long papers, the scout-to-map handoff also contains a temporary setting inventory. Construct it deterministically as follows:

1. normalize each scout `context_mentions[].name` only for exact case, whitespace, and punctuation comparison;
2. combine repeated exact names and preserve the union of their descriptions and SourceBlock IDs;
3. assign stable identifiers `CM001`, `CM002`, and so on in first-seen order;
4. require the map response to resolve every `CM` identifier to one generated Context identifier.

Every inventory identifier must occur exactly once in `context_mention_resolution`, and every value must refer to a generated Context. Several identifiers may resolve to the same Context. The table is referential mapping provenance, not a generated-label similarity test. Discard it when permanent Context IDs are assigned and do not ingest it into the scientific graph.

Only inexpensive structural validation is mandatory at this stage:

- schema validity;
- unique generated Context and Transition IDs;
- valid parent and endpoint references;
- parent-before-child resolvability and absence of cycles;
- root/child consistency of `split_reason`;
- valid SourceBlock references.

Do not require exact or fuzzy matching between LLM-generated labels and scout wording as a runtime validation gate. Semantic coverage is evaluated in the offline corpus regression suite and by reviewing the deterministic `paper_map.tree.txt` artifact.

A completed paper may be returned from cache only when its recorded prompt versions match the active prompt versions. On mismatch, fail with `STALE_DERIVED_ARTIFACTS`. An explicit `--rebuild-derived` run removes only `extraction/` and `final/`, retains the Nemotron parse, cleaned text, SourceBlocks, and SourceBlock embeddings, and rebuilds from paper mapping onward.


# 98. Final architectural summary

```text
                           PDF
                            │
                            ▼
                 Nemotron-Parse v1.2
                            │
                            ▼
                    raw structured parse
                            │
                            ▼
                    Markdown cleaning
                            │
                            ▼
                 stable SourceBlocks
                       (always)
                            │
                ┌───────────┴────────────┐
                │                        │
          <= 15k useful tokens      > 15k tokens
                │                        │
                ▼                        ▼
         whole-paper map          section scouts
                │                        │
                │                 map consolidation
                └───────────┬────────────┘
                            ▼
                    Context Registry
                            │
             ┌──────────────┴───────────────┐
             │                              │
             ▼                              ▼
      Context evidence                 Transition/
          bundles                     Claim bundles
             │                              │
             ▼                              ▼
      Facet extraction                Claim extraction
             │                              │
             └──────────────┬───────────────┘
                            ▼
                    late-context hints
                            │
                       if necessary
                            ▼
                      reconciliation
                            │
                            ▼
                    paper consolidation
                            │
                            ▼
                       validation
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
        required core              optional spatial
                                  resolution/enrichment
              │                           │
              └─────────────┬─────────────┘
                            ▼
                  conservative State
                    canonicalization
                            │
                            ▼
                    Qwen3 embeddings
                            │
                            ▼
                    final_paper.json
                            │
                            ▼
                 transactional Neo4j build
                            │
                            ▼
             graph + full-text + vectors
                            │
                            ▼
       context-aware scientific query pipeline
```

The most important implementation rule is:

> **Never chunk-and-extract independently. Map the paper first, preserve stable evidence IDs, and assemble raw evidence around known scientific objects.**

And the most important graph rule is:

> **A Claim is an evidence-bearing relationship scoped to a Context/Transition; it is not a universal causal edge.**
