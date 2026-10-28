# ClimateKG

ClimateKG is a context-conditioned scientific Knowledge Graph and GraphRAG
system for reasoning about land-use and land-cover effects on weather and
climate.

The system indexes scientific PDFs into provenance-linked SourceBlocks,
Contexts, Facets, Transitions, Claims, and canonical States. Queries are parsed
into explicit environmental conditions, gated against compatible Contexts,
searched for Claim paths, and answered with paper and SourceBlock citations.

## Authoritative Specifications

- `land_atmosphere_kg_indexing_pipeline.md`
- `land_atmosphere_kg_query_pipeline.md`
- `land_atmosphere_kg_problem_statement.md`
- `land_atmosphere_kg_project_summary.md`

The indexing and query specifications take precedence over implementation
shortcuts.

## Current Stack

- NVIDIA Nemotron Parse v1.2 for PDF parsing
- Qwen3.6-27B through Ollama for structured semantic stages
- Qwen3-Embedding-4B with 2048-dimensional embeddings
- Parquet tables as the default local graph materialization
- FAISS HNSW for Context, Claim, State, and Transition candidate retrieval
- Exact domain-aware Facet MaxSim after Context shortlisting
- Deterministic Python Claim gating and mechanism-path search
- Neo4j as an optional materialized graph and Cypher interface

## Repository Layout

```text
climatekg/        Python implementation and centralized constants.py settings
config/           State aliases, validation queries, and pipeline config
prompts/          Standalone prompts used by the application
scripts/          Indexing, validation, and export tools
tests/            Deterministic and pipeline-boundary tests
baselines/        Microsoft GraphRAG and Plain RAG implementations
visualizer/       Local artifact and graph browser
webapp/           Process-understanding and watershed-planning app
deployment/       Docker Compose, Airflow, Apache, and server setup
docs/             Core implementation references
```

Runtime data, PDFs, model weights, embeddings, LLM caches, and generated query
runs belong under `climatekg/runtime/` and are deliberately excluded from Git.

For Docker and Airflow deployment, start with
[`deployment/README.md`](deployment/README.md).

## Installation

```powershell
py -3.13 -m venv .venv-climatekg
.\.venv-climatekg\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv-climatekg\Scripts\python.exe -m pip install -e .
```

Required Ollama models:

```powershell
ollama pull qwen3.6:27b
ollama pull qwen3-embedding:4b
```

All indexing and query tuning values are defined in `climatekg/constants.py`.
The default `validated` reasoning profile uses medium reasoning for paper
mapping, no reasoning for the remaining indexing stages, and low/medium
reasoning for answer synthesis. `baseline` and `no` remain available for
controlled comparisons. Model names, stage settings, token budgets, `top_k`
values, thresholds, weights, parser paths, and timeouts are in the same file.
The older pipeline YAML files are retained only as historical configuration
snapshots and are not read at runtime.

Nemotron Parse and PDFium use the worker executables configured in
`climatekg/constants.py`. Missing parser requirements cause an explicit failure;
there is no alternate PDF-parser fallback.

Spatial and environmental enrichment uses Google Earth Engine only. Configure
`EARTH_ENGINE_PROJECT` as described in
[`docs/EARTH_ENGINE_ENRICHMENT.md`](docs/EARTH_ENGINE_ENRICHMENT.md). Local
rasters are not used as an automatic fallback.

## Index and Query

Index one or more PDFs:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli index "C:\papers\paper.pdf"
```

Build the Parquet graph and persisted FAISS indexes:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli build-parquet
```

Inspect graph and ANN counts:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli inspect-parquet
```

Run a query:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli query `
  "Under zero background wind, how does surface heterogeneity affect local clouds?" `
  --query-id Q000001
```

Every query preserves its parsed specification, scores, rejection reasons,
paths, selected evidence, LLM request envelopes, and cited answer under
`climatekg/runtime/outputs`.

## Validation

```powershell
python -m pytest tests -q -p no:cacheprovider
```

The ANN benchmark and Parquet storage design are documented in
`docs/ANN_MAXSIM_BENCHMARK.md` and `docs/PARQUET_GRAPH_BACKEND.md`.

## Visualizer

```powershell
.\visualizer\run_visualizer.ps1
```

Open `http://127.0.0.1:8765` to inspect Contexts, Facets, Claims, States,
SourceBlocks, provenance links, and saved query traces.

## Webapp Prototype

```powershell
.\webapp\run_webapp.ps1
```

Open `http://127.0.0.1:8780`. The prototype provides a direct scientific query
workflow and an India watershed-selection workflow that runs query-area
enrichment before the same context-aware retrieval pipeline. See
`webapp/README.md` for its local data and Earth Engine requirements.
