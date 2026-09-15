# ClimateKG Webapp Prototype

This local prototype exposes two workflows:

- **Process Understanding** submits a scientific question to the existing context-aware ClimateKG query pipeline.
- **Land use planning** selects an Indian watershed, enriches its geometry with the configured datasets, and asks the same pipeline for literature-grounded intervention evidence.

The browser performs no scientific scoring. It submits inputs, displays query stages, and renders the grounded answer and trace returned by `climatekg.query.run_query`.

## Run

Requirements:

- the project environment installed;
- Ollama running with `qwen3.6:27b` and `qwen3-embedding:4b`;
- Earth Engine authenticated for project `ee-atharv` for watershed enrichment;
- `assets/watershed_pan_india_simplified.geojson` present;
- the Parquet graph at `climatekg/runtime/outputs/three_system_benchmark/parquet_graph`.

On first use, `tiktoken` downloads its standard `o200k_base` vocabulary into `climatekg/runtime/cache/tiktoken`. The cache must be present when running without network access.

From the repository root:

```powershell
.\.venv-climatekg\Scripts\python.exe -m webapp.server --port 8780
```

Open <http://127.0.0.1:8780>.

To use another finalized Parquet graph:

```powershell
$env:CLIMATEKG_WEBAPP_GRAPH_ROOT = "F:\path\to\parquet_graph"
.\.venv-climatekg\Scripts\python.exe -m webapp.server --port 8780
```

Complete query reports, LLM requests/responses, enrichment output, and answers are written beneath `climatekg/runtime/webapp/queries`. This generated directory is excluded from Git.

Leaflet is included under `webapp/vendor/leaflet`. OpenStreetMap basemap tiles require network access. Watershed boundaries are always served from the local GeoJSON file.
