# Indexing Routes and Enrichment Status

Date: 2026-08-29

This document records the two implemented scientific-extraction routes and the
current status of spatial resolution and environmental enrichment. It describes
the code as it exists on branch `experiment/combined-v4-constrained-refs`.

## 1. The two indexing routes

Both routes start with the same PDF parser and cleaned `SourceBlock` objects.
Both routes also produce the same final `Context`, `Facet`, `Transition`, and
`Claim` schemas. Only the extraction procedure differs.

### 1.1 Staged extraction

Staged extraction is the current default production route.

```text
PDF
-> NVIDIA Nemotron Parse v1.2
-> cleaning and SourceBlocks
-> SourceBlock embeddings
-> paper map
-> permanent Context and Transition IDs
-> Facet extraction for each Context
-> Claim extraction for each Context or Transition
-> Context reconciliation
-> paper consolidation
-> State canonicalization
-> final object embeddings
-> final paper artifact and graph tables
```

For a staged paper with at most 15,000 cleaned tokens, the paper map receives
the complete cleaned paper. A longer paper is divided into section-sized inputs;
section scouts are consolidated into one paper map before the later extraction
calls.

Advantages:

- each LLM request has a narrow task and a smaller scientific scope;
- complex crossed experimental regimes can be represented in the paper map;
- failures can be traced to a specific mapping, Facet, or Claim call.

Costs:

- it uses multiple LLM calls per paper;
- repeated evidence and context descriptions increase indexing time.

The implementation is in `climatekg/indexer.py` and `climatekg/extract.py`.
Exact requests and responses are stored below each paper's `mapping/` and
`extraction/` artifact directories.

### 1.2 Combined extraction

Combined extraction is an experimental route for short cleaned papers. It is
currently disabled by default by `combined_extraction_enabled = False`.

```text
PDF
-> NVIDIA Nemotron Parse v1.2
-> cleaning and SourceBlocks
-> SourceBlock embeddings
-> one nested Context/Facet/Transition/Claim LLM request
-> deterministic conversion to the final flat schemas
-> strict provenance and reference checks
-> Context reconciliation
-> paper consolidation
-> State canonicalization
-> final object embeddings
-> final paper artifact and graph tables
```

The preferred size is approximately 8,000 cleaned tokens. The current hard
safety limit is 16,000 cleaned tokens. Token count is calculated after removing
reference blocks and empty blocks.

The LLM receives short request-local evidence handles such as `E001`, while
deterministic Python maps those handles back to permanent `SourceBlock` IDs.
Facets and Context-scoped Claims are nested within their Context, and
Transition-scoped Claims are nested within their Transition. This reduces
invalid cross-references without changing the final graph schema.

Advantages:

- one main scientific-extraction call substantially reduces call overhead;
- nesting makes local references easier for the model to produce correctly.

Current limitation:

- one call can compress or omit crossed experimental regimes in structurally
  complex papers, even when the paper is short enough for the token limit.
  Eligibility therefore cannot ultimately be decided by token count alone.

The implementation is in `climatekg/small_paper.py` and
`climatekg/combined_extraction.py`; the standalone prompt is
`prompts/small_paper_extraction.txt`. Detailed examples are in:

- `docs/COMBINED_V41_P000010_REPORT.md`
- `docs/COMBINED_V41_HETEROGENEOUS_PATCH_REPORT.md`
- `docs/COMBINED_EXTRACTION_FAILURE_RCA.md`

## 2. What both routes share

After extraction, both routes use the same reconciliation, consolidation,
State canonicalization, embedding, and graph-output code. A final artifact
records `metadata.extraction_route` as either `staged` or
`small_paper_combined`, so results remain auditable.

The combined route is not a different scientific graph design. It is only a
different way to obtain the same validated extraction objects.

## 3. Enrichment specified versus implemented

The authoritative specifications define an optional deterministic enrichment
stage. Optional means that unresolved geometry must not block indexing. It does
not mean that an LLM should guess missing geography or environmental conditions.

The specified design includes:

- deterministic named-place resolution through a versioned gazetteer or
  application registry;
- a shared enrichment implementation for indexed papers and queries;
- polygon or point summaries for climate regime, aridity, seasonal wind,
  terrain, and supported land-surface configuration;
- provenance containing dataset, version, temporal window, geometry hash, and
  algorithm version;
- derived `Facet` objects marked with `origin = "derived"`.

### Current implementation status

| Capability | Current status |
|---|---|
| `SpatialSupport` schema with optional geometry | Implemented |
| Derived-Facet provenance schema | Implemented |
| Enrichment thresholds in central configuration | Present |
| Deterministic named-place resolver | Not implemented |
| Gazetteer or application-registry adapter | Not implemented |
| Climate/aridity/wind/terrain raster calculations | Not implemented |
| Shared indexing/query enrichment functions | Not implemented |
| Separate geographic overlap or distance score | Not implemented |

There is no active enrichment phase in `climatekg/indexer.py`. The query parser
also does not geocode a place name. It creates a `SpatialSupport` containing the
name, sets `geometry` to `null`, sets resolution to `unresolved`, and records:

```text
QUERY_ENRICHMENT_SKIPPED_UNRESOLVED_SPATIAL_SUPPORT
```

The place name is included in the query-context embedding text. Consequently,
current location matching is semantic text similarity, not geographic matching.
The system cannot currently calculate polygon overlap, physical distance, or
environmental similarity for a new place.

## 4. Have study-area coordinates been extracted?

Only occasionally. The extraction schemas allow a paper to report geometry, and
the LLM sometimes copies explicit coordinates from the paper. There is no
deterministic coordinate extractor or geocoder, so named areas are not converted
to latitude/longitude automatically.

Observed artifact audit:

| Artifact set | Final papers | Contexts | Contexts with named spatial support | Non-null geometry |
|---|---:|---:|---:|---:|
| Main `runtime/data/papers` corpus | 10 | 101 | 32 | 0 |
| 2026-08-28 indexing benchmark | 7 | 63 | 33 | 2 |
| Combined-versus-staged combined outputs | 7 | 46 | 28 | 0 |

The two benchmark geometries are explicit San Gorgonio observation points:

```text
upwind:   latitude 33.896, longitude -116.604
downwind: latitude 33.875, longitude -116.562
```

Other experiment artifacts contain a few copied coordinate ranges, but their
representations are inconsistent: numeric point fields, numeric arrays, and
string ranges all occur. These values are not yet a reliable normalized spatial
index.

Therefore, the direct answer is:

- explicit latitude/longitude may be retained when the paper clearly reports it;
- most existing study locations have names but no geometry;
- latitude/longitude is not currently derived for named study areas;
- current graph retrieval must not be described as geographic matching.

## 5. Consequence for in-corpus and out-of-corpus queries

For an in-corpus query that repeats a paper's location and conditions, semantic
similarity can be high because the same place name and Facet language occur in
both query and indexed Context text. This is a textual match and can overstate
the importance of the location itself.

For an out-of-corpus location, the location name may have little textual
similarity to indexed locations even when its climate, terrain, wind, and land
surface are scientifically comparable. Without resolved geometry and the shared
environmental enrichment functions, the system cannot expose that comparability.

Conversely, two places with similar names or broad regional wording can receive
some semantic similarity without being environmentally transferable. Claim
gating should therefore not treat the present location-name embedding as a
geographic applicability test.

## 6. Required work before a fair location-transfer experiment

1. Define and validate one normalized geometry representation for points,
   polygons, and supported regional bounds.
2. Implement the specification's deterministic resolver precedence and retain
   ambiguity instead of choosing an arbitrary gazetteer result.
3. Implement the shared indexing/query enrichment functions for the first small
   set of configured datasets.
4. Re-enrich indexed Contexts and new query areas with identical dataset
   versions, temporal windows, algorithms, and description rendering.
5. Report geographic resolution, environmental Context similarity, coverage,
   intervention similarity, and mechanism relevance as separate values.
6. Then compare paired query sets: known corpus locations, new locations with
   similar environmental conditions, and new locations with deliberate
   environmental mismatches.

Until those steps are implemented, we can test retrieval behavior for known and
new place names, but the result measures text retrieval rather than the intended
location-transfer capability.
