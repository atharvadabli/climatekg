# LULC Plain RAG Pipeline

This folder contains the current plain RAG baseline for literature-backed land-use recommendations.

The system is intentionally simple:

1. Chunk parsed paper markdown.
2. Embed chunks with Ollama.
3. Add metadata filters for climate regime, intervention, stressor, mechanism, and region.
4. Retrieve relevant evidence.
5. Use the retrieved evidence for watershed-level screening and future portal recommendations.

## Inputs

Parsed literature:

```text
E:\Atharv\lit_200\parsed_pdfs
```

Main parsed-paper index:

```text
E:\Atharv\lit_200\parsed_pdfs\parsed_papers.csv
```

Koppen/study-area classification:

```text
E:\Atharv\lulc_suggestor_poc\manuallly_extracting_with_agent\categorized_by_koppen\classification_manifest.csv
```

Portal/watershed assets:

```text
E:\Atharv\lulc_suggestor_poc\13jul
```

Main watershed file:

```text
E:\Atharv\lulc_suggestor_poc\13jul\assets\watershed_pan_india_simplified.geojson
```

Portal metric files used:

```text
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\aridity_by_watershed.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\ef_proxy_by_watershed.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\tci_proxy_by_watershed.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\dtr_by_watershed.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\ctphi_triggerability_samples.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\lulc_terrain_samples.csv
E:\Atharv\lulc_suggestor_poc\13jul\assets\coupling_metrics\gldas_true_coupling_samples.csv
```

## Models

Ollama models:

```text
Embedding: qwen3-embedding:4b
Answering: qwen3.6:27b
```

Check models:

```powershell
ollama list
```

Pull if missing:

```powershell
ollama pull qwen3-embedding:4b
ollama pull qwen3.6:27b
```

## Core Files

```text
plain_rag.py
run_watershed_rag.py
README.md
PIPELINE_README.md
```

`plain_rag.py` handles:

- paper loading
- markdown section chunking
- embeddings
- local JSONL vector index
- metadata enrichment
- metadata-aware retrieval
- answer generation with Ollama

`run_watershed_rag.py` handles:

- loading portal watershed assets
- joining coupling metrics
- deriving rough climate/stressor/intervention filters
- running RAG retrieval for sampled watersheds
- writing portal-ready CSV/JSON/Markdown outputs

## Build Literature Index

Build from scratch:

```powershell
python plain_rag.py build
```

Current index location:

```text
rag_index\chunks.jsonl
rag_index\meta.json
```

Current index state:

```text
papers: 104
chunks: 2156
embedding model: qwen3-embedding:4b
chunking: markdown sections, 750 words, 120-word overlap, minimum 80 words
```

## Enrich Existing Index

If embeddings already exist, enrich metadata without recomputing embeddings:

```powershell
python plain_rag.py enrich-index
```

Metadata added per chunk:

```text
koppen_category
koppen_confidence
koppen_rationale
climate_groups
koppen_codes
interventions
stressors
mechanisms
regions
evidence_role
```

`evidence_role` is used to prefer direct studies over broad reports, reviews, methods papers, and background framework papers.

## Metadata-Aware Search

Use `search` to inspect retrieval without waiting for the answer model:

```powershell
python plain_rag.py search --region india --climate-group dry --koppen-code BSh --stressor extreme_heat --intervention afforestation "Can tree cover reduce heat in semi-arid Rajasthan?"
```

Use strict filters when a field must match:

```powershell
python plain_rag.py search --strict-intervention --intervention irrigation --stressor extreme_heat --mechanism evapotranspiration "How does irrigation affect hot extremes in Indian or climate-analog regions?"
```

Useful flags:

```text
--region
--climate-group
--climate-category
--koppen-code
--intervention
--stressor
--mechanism
--strict-intervention
--strict-stressor
--strict-mechanism
--strict-region
--strict-climate
--exclude-cold
```

## Ask A RAG Question

Example:

```powershell
python plain_rag.py query --region india --climate-group dry --koppen-code BSh --stressor extreme_heat "For a semi-arid Indian micro-watershed, which land-use interventions can reduce extreme heat, and what mechanisms and caveats apply?"
```

The output includes:

- synthesized answer
- source list
- vector score
- metadata boost
- metadata reasons
- chunk path
- metadata tags

## Watershed Batch Run

Run:

```powershell
python run_watershed_rag.py
```

Outputs:

```text
query_outputs\watershed_runs\all_india_watershed_screening.csv
query_outputs\watershed_runs\selected_watershed_rag_retrieval.json
query_outputs\watershed_runs\selected_watershed_rag_retrieval.md
query_outputs\watershed_runs\selected_watershed_recommendations.csv
```

Current behavior:

- Screens all 4,565 watersheds from `watershed_pan_india_simplified.geojson`.
- Uses aridity, EF proxy, TCI proxy, DTR, and available sampled metrics.
- Produces stressor and candidate-intervention fields for all watersheds.
- Runs RAG retrieval for watersheds with richer sampled metrics:
  - `B20SAR01`
  - `C05CAM63`
  - `C2ABHG31`

The all-India screening CSV contains:

```text
wsconc
area_sqkm
bacode
sbcode
aridity_index
aridity_regime
climate_group
koppen_code
temperature_lever
humidity_lever
precipitation_lever
wind_lever
stressors
candidate_interventions
```

The selected recommendation CSV contains:

```text
watershed_id
rank
intervention
rank_score
confidence
where
expected_effect
mechanisms
caveat
```

## Current Screening Logic

The watershed runner mirrors the portal idea:

1. Use coupling metrics to decide which stressors are plausibly influenceable.
2. Convert local variables to retrieval filters.
3. Retrieve literature mechanisms and caveats.
4. Emit ranked intervention suggestions.

Current stressor mapping:

- `Temperature/LST` medium/high -> `extreme_heat`
- `Humidity/VPD` medium/high -> `agricultural_drought`
- `Precipitation` medium/high -> `rainfall_shift`
- `Wind` medium/high -> `dust_wind`

Current candidate interventions:

- `afforestation / agroforestry / shelterbelts`
- `irrigation efficiency / water spreading / supplemental irrigation`
- `cropping practice change / cover crops / residue / reduced tillage`

This is a screening layer, not a physical simulation.

## Portal Integration Direction

The portal at:

```text
E:\Atharv\lulc_suggestor_poc\13jul
```

already supports:

- watershed selection
- wind diagnostics
- aridity metrics
- EF proxy
- TCI proxy
- DTR
- sampled CTP-HI triggerability
- sampled LULC terrain metrics
- sampled GLDAS true coupling

Recommended next integration:

1. User selects watershed in Streamlit.
2. Portal reads watershed metrics.
3. Portal maps metrics to:
   - `region`
   - `climate_group`
   - `koppen_code`
   - `stressors`
   - `candidate_interventions`
4. Portal calls retrieval logic from `plain_rag.py`.
5. Portal displays:
   - ranked recommendations
   - where to intervene
   - expected effect direction
   - mechanism chain
   - confidence
   - caveats
   - source papers/chunks

## Important Limitations

- The RAG index is still a plain JSONL vector index, not a full mechanism KG.
- Metadata tags are rule-based and should be audited.
- Koppen classification is paper-level, not chunk-level.
- India climate mapping is currently coarse.
- Only three watersheds currently have full sampled CTP-HI/LULC/GLDAS metrics.
- The recommendation scores are screening heuristics, not calibrated impact estimates.
- The system should not claim physical certainty or substitute for WRF/SWAT/crop modeling.

## Next Engineering Steps

1. Add more LULC terrain samples for all selected watersheds.
2. Add watershed-level Koppen classes from an actual raster or lookup instead of aridity-derived approximation.
3. Expand intervention set:
   - wetland restoration
   - check dams / tanks / reservoirs
   - riparian buffers
   - windbreaks
   - paddy/rice conversion
   - solar/wind farm caveats
4. Move recommendation scoring into a separate module shared by CLI and portal.
5. Add citation-aware final answer generation per watershed.
6. Start extracting typed mechanism KG edges from retrieved chunks.

