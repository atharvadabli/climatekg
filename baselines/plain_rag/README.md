# Plain Ollama RAG

This is a minimal local RAG baseline for the parsed papers in:

```text
E:\Atharv\lit_200\parsed_pdfs
```

It reads `parsed_papers.csv`, splits each referenced `document.md` by markdown
sections/headings, chunks within large sections, embeds chunks with Ollama, stores a local
JSONL vector index, enriches chunks with climate/intervention/stressor/mechanism metadata,
and answers questions with retrieved excerpts.

## Models

Defaults:

```text
Embedding: qwen3-embedding:4b
Answering: qwen3.6:27b
```

Make sure Ollama is running and the models are available:

```powershell
ollama pull qwen3-embedding:4b
ollama pull qwen3.6:27b
```

## Build The Index

```powershell
python plain_rag.py build
```

This writes:

```text
rag_index\chunks.jsonl
rag_index\meta.json
```

## Ask Questions

```powershell
python plain_rag.py query "What are the climate impacts of afforestation?"
```

Useful options:

```powershell
python plain_rag.py build --chunk-words 750 --overlap-words 120 --min-chunk-words 80 --batch-size 8
python plain_rag.py query --top-k 8 "How does irrigation affect land surface temperature?"
```

The answer includes source tags such as `[S1]`, followed by the retrieved source paths.

## Farmer-Friendly Response Comparisons

`simplify_query_outputs.py` rewrites representative saved portal responses with
Ollama and the fixed term translations in `farmer_vocabulary.json`. It preserves
the original response, stores a structured simplification, and builds a standalone
side-by-side HTML comparison page.

Run the default arid, semi-arid, and humid examples:

```powershell
python simplify_query_outputs.py
```

Outputs:

```text
query_outputs\simplified\farmer_response_comparisons.json
query_outputs\simplified\farmer_response_comparisons.html
```

Supply different saved portal JSON files if needed:

```powershell
python simplify_query_outputs.py query_outputs\portal_app\example_one.json query_outputs\portal_app\example_two.json
```

The three featured ideal responses are stored in:

```text
ideal_farmer_response.json
ideal_farmer_responses\B20SAR01.json
ideal_farmer_responses\C05CAM63.json
```

Rebuild the HTML after editing them without calling Ollama:

```powershell
python simplify_query_outputs.py --render-only
```

## Metadata-Aware Retrieval

The build uses the Koppen classification manifest by default:

```text
E:\Atharv\lulc_suggestor_poc\manuallly_extracting_with_agent\categorized_by_koppen\classification_manifest.csv
```

If you already built the index, enrich it without recomputing embeddings:

```powershell
python plain_rag.py enrich-index
```

Inspect retrieval without waiting for the answer model:

```powershell
python plain_rag.py search --region india --stressor extreme_heat --intervention afforestation "Can tree cover reduce heat in semi-arid Rajasthan?"
```

Use climate filters and boosts:

```powershell
python plain_rag.py search --region india --climate-group dry --koppen-code BSh "What land-use interventions reduce heat in semi-arid India?"
```

Strict filters require matching metadata:

```powershell
python plain_rag.py search --strict-intervention --intervention irrigation --strict-climate --climate-group dry "How does irrigation affect hot extremes in dry regions?"
```

Available metadata flags:

```text
--intervention       afforestation, deforestation, irrigation, cropland_expansion, wetland_restoration, reservoir_tank, wind_farm, solar_farm, rice_paddy
--stressor           extreme_heat, agricultural_drought, rainfall_shift, flood_peak, dust_wind
--mechanism          evapotranspiration, albedo, roughness, soil_moisture, runoff_streamflow, moisture_recycling, cloud_cover, convection, carbon
--region             india, south_asia, sahel, amazon, europe, china, australia, himalaya
--climate-group      tropical, monsoon, dry, semi_arid, arid, temperate, continental, highland, mixed, global
--climate-category   Af_Am_Aw_tropical, BSh_BWh_BWk_dry, Cfa_Cwa_Cfb_temperate, Dfa_Dfb_Dwa_continental, ET_Dwc_highland, mixed_global_multiple_koppen
--koppen-code        Af, Am, Aw, BSh, BWh, BWk, Cfa, Cwa, Cfb, Dfa, Dfb, Dwa, ET, Dwc
```
