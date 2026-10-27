# Deployment architecture

## Services

| Service | Public | Responsibility |
|---|---|---|
| Apache | Yes, HTTPS | TLS termination and reverse proxy |
| Backend | Localhost only | Static frontend, public API, job submission/status |
| Airflow webserver | Localhost only | DAG API and restricted operator UI |
| Airflow scheduler | No | Schedules and retries DAG tasks |
| PostgreSQL | No | Airflow metadata |
| Computation service | No | Runs ClimateKG, GraphRAG, or Plain RAG |
| Ollama | No | Local generation and embedding models |

The computation service is persistent so the 115-paper corpus, Parquet graph,
FAISS indexes, and baseline indexes remain available between jobs. A process
lock permits one inference job at a time. Airflow also sets `max_active_runs=1`
because the default deployment assumes one GPU.

## Request flow

1. The browser posts to `/api/process-query` or `/api/land-use-plan`.
2. The backend validates the request and writes
   `/artifacts/jobs/<job_id>.json` with status `queued`.
3. The backend triggers `climatekg_query` through Airflow's authenticated API.
4. Airflow calls `POST /internal/jobs/<job_id>/run` on the private computation
   service using a bearer token.
5. The computation service changes the job to `running`, invokes the existing
   `ClimateKGEngine`, and appends every reported stage to the job record.
6. The service writes either the complete result or a visible failure.
7. The browser polls `/api/jobs/<job_id>` until status is `complete` or `failed`.

Airflow carries only the job ID. Scientific prompts, geometries, evidence, and
answers remain in the shared artifact store and existing query artifact paths.

## Persistence and restart behavior

- Backend restart: jobs remain readable from the shared directory.
- Airflow restart: DAG state remains in PostgreSQL.
- Computation restart during inference: Airflow retries once. A job left as
  `running` must be inspected before manual retry to prevent duplicate work.
- Ollama restart: the mounted model store prevents model re-download.
- Host restart: `restart: unless-stopped` restarts long-running services.

## Trust boundaries

- Only Apache is exposed to the internet.
- Backend and Airflow bind to host loopback addresses.
- Computation and Ollama are reachable only on the Compose network.
- Airflow-to-computation calls require `CLIMATEKG_INTERNAL_TOKEN`.
- Earth Engine credentials are mounted read-only.
- The data/index mount is read-only; only the artifact mount is writable.
