# Deployment implementation status

## Completed

The server deployment path has been implemented and documented. It supports the
following request flow:

```text
browser -> web backend -> Airflow -> computation service
        -> job record -> web backend -> browser
```

The repository now contains:

- Docker images for the web backend and computation service;
- a Docker Compose stack for the application and Airflow services;
- an Airflow DAG that submits ClimateKG work and records progress and results;
- persistent job records under the mounted artifacts directory;
- environment-variable configuration for data, models, indexes, and services;
- Apache reverse-proxy guidance for HTTPS deployment;
- installation, operation, backup, retry, and troubleshooting instructions;
- a local execution mode that remains available for development.

The browser API contract is unchanged. In Airflow mode, the backend submits a
job and the browser polls the existing job endpoint until it reaches a terminal
state.

## Validation completed on this integration branch

- Complete Python suite: 141 passed when run with the existing local
  `o200k_base` tokenizer cache and a writable test-temp directory. The first
  run without that cache failed on network downloads and temp setup.
- Focused orchestration, webapp, evidence-subgraph and semantic-link tests: 21 passed.
- Docker Desktop Linux engine became accessible and the Compose file passed
  `docker compose config --quiet` using the ignored local `deployment/.env`.
- The 115-paper Parquet graph and all three baseline index directories exist at
  the configured read-only mount path.
- The same code started locally at `http://127.0.0.1:8781/`; its config API
  reported the graph, baseline indexes, watershed GeoJSON and Koppen asset ready.
- A local Microsoft GraphRAG process query completed through the browser-facing
  job API and saved an answer trace with 10 retrieved evidence entries under
  `climatekg/runtime/deployment/queries/WEB_20261027_211157_7a4511`.
  This checks integration, not scientific correctness: the answer incorrectly
  expanded `MSE` as "moisture-equivalent" rather than moist static energy.

## Remaining deployment check

An actual image build and end-to-end container startup were **not** completed.
Docker Hub token retrieval for `python:3.13-slim` timed out. The host could not
connect to `auth.docker.io:443`; `mirror.gcr.io:443` was also unreachable, and
the Python image is not cached locally. This is a network/download blocker,
not evidence that the app image builds successfully. Airflow, Postgres and
Ollama images are also not cached. Do not report Docker/Airflow E2E as passed.

Earth Engine credentials were not found at the checked default gcloud path;
watershed enrichment has not been container-tested. Process questions do not
need those credentials.

When container downloads work again, from this integration worktree:

```powershell
docker compose --env-file deployment/.env -f deployment/docker-compose.yml build backend compute
docker compose --env-file deployment/.env -f deployment/docker-compose.yml up -d
docker compose --env-file deployment/.env -f deployment/docker-compose.yml ps
```

Then run one process-understanding query and one land-use-planning query, verify
their Airflow task logs, job records, citations, and browser results, and record
the tested image tags. No deployment code change is required before that check.
