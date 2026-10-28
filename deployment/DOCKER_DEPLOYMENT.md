# Docker deployment

## Mounted data

The image contains code and Python libraries. It does not contain papers,
indexes, model weights, credentials, or generated results.

| Host setting | Container path | Access |
|---|---|---|
| `CLIMATEKG_DATA_DIR` | `/data` | Read-only |
| `CLIMATEKG_MODELS_DIR` | `/root/.ollama` | Ollama read/write |
| `CLIMATEKG_ARTIFACTS_DIR` | `/artifacts` | Shared read/write |
| `CLIMATEKG_CREDENTIALS_DIR` | `/credentials` | Read-only |
| `CLIMATEKG_ASSETS_DIR` | `/app/assets` | Read-only |

The code is built from the checked-out Git revision. Rebuild `backend` and
`compute` after pulling code changes. Data and model updates do not require an
image rebuild.

## Commands

```bash
# Validate resolved variables and mounts.
docker compose config

# Start or stop.
docker compose up -d
docker compose down

# Show health and logs.
docker compose ps
docker compose logs -f backend airflow-scheduler compute

# Rebuild after git pull.
docker compose build backend compute
docker compose up -d --no-deps compute backend
```

Do not use `docker compose down -v` during normal operation. The `-v` option
removes the Airflow PostgreSQL volume and therefore its run history.

## Model management

The one-shot `ollama-models` service verifies/pulls both configured models on
startup. To inspect the model store:

```bash
docker compose exec ollama ollama list
```

On Windows with Docker Desktop/WSL, the containerized Ollama process may fail
to allocate a large CUDA buffer even when `nvidia-smi` reports free VRAM. If
the same model loads in native Windows Ollama, set
`CLIMATEKG_OLLAMA_URL=http://host.docker.internal:11434` in the ignored
`deployment/.env` and recreate `compute` and `backend`. The app still runs in
Docker; only inference uses native Windows Ollama. Keep the native Ollama server
running. On Linux, leave this variable unset to use the containerized server.

Pin `OLLAMA_IMAGE` to a tested version before production deployment. When
upgrading Ollama, test both structured JSON generation and 2,048-dimensional
embedding requests before changing the pin.

## Data/index upgrades

1. Stop new job submission.
2. Wait for the current DAG run to finish.
3. Build the replacement data directory separately.
4. Validate its Parquet manifest and baseline indexes.
5. Change `CLIMATEKG_DATA_DIR` or atomically replace the mounted directory.
6. Restart `compute` and `backend`.

Record the Git revision and index manifest used for publication experiments.

## Backup

Back up:

- `CLIMATEKG_ARTIFACTS_DIR`, including job and query traces;
- the `airflow-postgres` Docker volume;
- deployment `.env` through a secret-management system;
- index manifests and the script/configuration used to rebuild them.

Model weights and derived indexes can be recreated, but backing them up may save
substantial download and computation time.
