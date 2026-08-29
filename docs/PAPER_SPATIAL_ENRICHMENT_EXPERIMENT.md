# Paper Spatial Enrichment Experiment

## Purpose

Test whether paper study settings can receive the same derived environmental
Facets as location-conditioned queries, without adding another LLM call.

## Existing Pipeline

Paper enrichment was already placed correctly after consolidation and before
embeddings. A resolved setting receives derived climate, aridity, wind,
terrain, and land-cover Facets. Those Facets enter the setting retrieval text,
while Claims retain their paper evidence and are not converted into dataset
findings.

The existing resolver handled only:

1. valid geometry already returned by extraction;
2. text in the narrow form `latitude ..., longitude ...`;
3. an exact application watershed ID.

It had no gazetteer implementation.

## Corpus Audit

The ten finalized papers contained 32 non-null spatial-support records, but no
valid geometry. Five records incorrectly used `resolution="exact"` with null
geometry.

The available 17-paper portion of the 50-paper benchmark contained 62 spatial
supports. Only two had non-null geometry, and both used non-GeoJSON range
objects. Four records used exact resolution with null geometry. Therefore the
paper enrichment stage emitted no derived Facets in these saved runs.

Coordinate-like text was not a reliable success measure. Some matches were
variable names, station tables, latitude-only flight tracks, or locations from
background discussion rather than the analyzed setting.

## Changes Tested

- The existing Qwen mapping prompts now define Point and Polygon GeoJSON
  completely, including longitude-first order and Polygon ring nesting.
- Mapping output uses a typed geometry schema. Invalid range dictionaries,
  invalid coordinate nesting, out-of-range positions, unclosed rings, and
  exact resolution with null geometry are rejected before enrichment.
- No new LLM call was added to the indexing pipeline.
- ERA5-Land monthly wind aggregation now uses one area-weighted multiband
  reduction instead of 360 concurrent reductions.
- Broad-region and native-pixel limits are explicit configuration values with
  visible skip reasons.

## P000015 Trace

The old map represented the model domain as:

```json
{"lat_range":[8,-45],"lon_range":[-35,-90]}
```

This was not GeoJSON and could not be enriched.

Replaying the full 54 KB consolidation input found the correct reported bounds
but took 658.5 seconds. It returned a Polygon missing one ring-nesting level.
The tightened typed schema rejects that result. A focused constrained-schema
smoke test on the original domain passage took 7.1 seconds and returned:

```json
{
  "kind": "region",
  "name": "southern part of South America",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[-35.0,-8.0],[-90.0,-8.0],[-90.0,-45.0],[-35.0,-45.0],[-35.0,-8.0]]]
  },
  "resolution": "approximate"
}
```

The first enrichment attempt failed because 360 per-month wind reductions
exceeded Earth Engine's concurrent-aggregation limit. The multiband algorithm
removed that failure. Native 10 m WorldCover and 30 m SRTM were then too large
for the continental rectangle. Per-family pixel checks made those skips
explicit. A later run completed in 44.5 seconds, but only 44-47% of the
rectangle had valid land data and its spatially averaged wind was not a local
condition. The final broad-region eligibility check now stops this case before
raster calls. The explicit skip completed in 6.5 seconds and emitted the area
and configured threshold.

Local artifacts are under:

```text
climatekg/runtime/outputs/paper_spatial_enrichment_experiment/P000015/
```

## Main Risks

1. **Study-setting binding:** coordinates can describe an initialization
   station, cited study, inset map, or excluded subregion rather than the
   current setting.
2. **Parser representation:** degree symbols, LaTeX `circ`, DMS tables,
   hemisphere letters, en dashes, and figure-only map bounds vary widely.
3. **Named places:** a place name without coordinates requires a versioned
   gazetteer. Ambiguous names must remain unresolved.
4. **Scale:** a bounding rectangle for a continental model is not local
   support and can include large ocean areas.
5. **Scenario mismatch:** 2021 WorldCover does not describe historical land
   cover or a simulated counterfactual treatment.
6. **Temporal mismatch:** 1986-2010 Koppen and 1991-2020 reanalysis are
   background climatologies, not observations for every paper period.
7. **Hierarchy:** repeated geometry on parent and child settings can duplicate
   derived Facets. Prefer the shallowest valid geographic setting and let
   descendants inherit it.
8. **Retrieval interpretation:** matching derived dataset Facets improves
   applicability ranking, but does not turn a retrieved Claim into stronger
   evidence or a probability of truth.

## Recommended Minimal Path

1. Keep spatial extraction inside the existing mapping call and retain the
   typed schema validation.
2. Add a deterministic, versioned gazetteer cache for exact polygon and point
   matches with administrative/country qualifier checks. Do not use an LLM to
   invent coordinates or select ambiguous candidates.
3. Enrich exact points and local polygons only. Keep broad, global,
   idealized, latitude-only, and moving-track settings unresolved unless an
   appropriate geometry is explicitly available.
4. Initially exclude WorldCover from paper scenario enrichment unless its date
   and meaning are compatible with the observed setting. Continue using it for
   current-area query enrichment.
5. Attach a derived Facet once at the shallowest context sharing a geometry;
   descendants receive it through normal context inheritance.
6. Add a persistent cache keyed by geometry hash, dataset/version, temporal
   window, and algorithm version. The present cache is only per paper.
7. After exact geometry yield improves, batch multiple Earth Engine polygons
   with `reduceRegions`; do not add this complexity before the corpus contains
   enough resolvable local sites to justify it.

## Status

The geometry schema and prompt changes are usable. The full paper-enrichment
feature should remain experimental until named-place resolution, scenario-safe
land-cover handling, shallowest-context attachment, and a local-site corpus
test are completed.
