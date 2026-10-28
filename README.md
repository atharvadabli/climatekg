# ClimateKG

ClimateKG answers questions about how land-use changes affect weather and
climate. It keeps each paper's findings attached to its study conditions and
source passages. The webapp has **Process Understanding** for literature
questions and **Land use planning** for Indian watersheds. Users can choose
ClimateKG, Microsoft GraphRAG, or Plain RAG.

This README covers serving an **already-built index** on Ubuntu 24.04
`x86_64`. PDF indexing is separate. The repository does not include PDFs,
graph data, watershed assets, model weights, or credentials. Supply those
artifacts before starting the stack.

## Services and Libraries

```text
browser -> backend -> Airflow -> computation service -> Ollama
                    <- saved job and query trace <-
```

Docker Compose starts the web backend, computation service, Airflow scheduler
and webserver, PostgreSQL, and Ollama. The first start pulls `qwen3.6:27b`
and `qwen3-embedding:4b`. The application image uses Python 3.13 and installs
Pydantic, PyArrow, NumPy, FAISS CPU, tiktoken, Earth Engine API, Pillow,
Rasterio, pandas, graspologic-native, `curl`, `libexpat1`, and `libgomp1`.
Airflow uses a separate Python 3.12 image. **No Python libraries need to be
installed on the Linux host.** See [`pyproject.toml`](pyproject.toml) for the
Python dependency ranges.

## Linux Prerequisites

- Ubuntu 24.04 `x86_64`, Git, and disk space for the index, images, and roughly
  20 GB of model downloads.
- An NVIDIA GPU with enough free VRAM for Qwen3.6-27B at the configured
  context size. A 24 GB GPU is a starting point, not a guarantee; test the
  actual server without other GPU workloads.
- NVIDIA driver, Docker Engine with the Compose plugin, and NVIDIA Container
  Toolkit. Follow the [Docker Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/)
  and [NVIDIA toolkit guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide/).
- Network access to Docker Hub, Ollama model downloads, and Google Earth
  Engine. Watershed planning requires an Earth Engine-enabled project and
  credentials; process questions do not.

Verify the host before deployment:

```bash
docker compose version
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
```

## 1. Clone and Supply Data

```bash
sudo mkdir -p /opt/climatekg
sudo chown "$USER:$USER" /opt/climatekg
git clone --branch integration/production-clean-v1 https://github.com/atharvadabli/climatekg.git /opt/climatekg/app
cd /opt/climatekg/app
sudo mkdir -p /srv/climatekg/{data,assets,models,artifacts,credentials}
sudo chgrp -R 0 /srv/climatekg/artifacts
sudo chmod -R 2770 /srv/climatekg/artifacts
```

Copy a completed, compatible index and the two map assets to these paths:

```text
/srv/climatekg/data/parquet_graph/manifest.json
/srv/climatekg/data/parquet_graph/*.parquet
/srv/climatekg/data/parquet_graph/ann/
/srv/climatekg/data/baselines/graphrag/
/srv/climatekg/data/baselines/plain_rag/index/
/srv/climatekg/assets/watershed_pan_india_simplified.geojson
/srv/climatekg/assets/Global_1986-2010_KG_5m.kmz.zip
```

The graph and baseline indexes must come from the same corpus. The current
demo index is generated data kept outside Git; an empty mount cannot answer
questions. Data and assets mount read-only. See
[`deployment/DATA_BUNDLE.md`](deployment/DATA_BUNDLE.md) to package, privately
host, verify, and extract the complete serving bundle. See
[`deployment/DOCKER_DEPLOYMENT.md`](deployment/DOCKER_DEPLOYMENT.md) for index
replacement and backups.

## 2. Configure Earth Engine

For watershed planning, put application-default credentials for a dedicated
service identity at
`/srv/climatekg/credentials/application_default_credentials.json` and grant
that identity Earth Engine access. The image also accepts an
`earthengine authenticate` file at `/srv/climatekg/credentials/credentials`
for local testing. Keep credentials readable by the app container and never
commit them. There is no local-data fallback if enrichment fails.

## 3. Configure and Start

```bash
cd /opt/climatekg/app
cp deployment/.env.example deployment/.env
openssl rand -hex 32
```

Edit `deployment/.env` with a generated token, strong password, absolute host
paths, and your Earth Engine project:

```dotenv
CLIMATEKG_INTERNAL_TOKEN=<random-hex-token>
AIRFLOW_ADMIN_PASSWORD=<strong-password>
CLIMATEKG_DATA_DIR=/srv/climatekg/data
CLIMATEKG_ASSETS_DIR=/srv/climatekg/assets
CLIMATEKG_MODELS_DIR=/srv/climatekg/models
CLIMATEKG_ARTIFACTS_DIR=/srv/climatekg/artifacts
CLIMATEKG_CREDENTIALS_DIR=/srv/climatekg/credentials
EARTH_ENGINE_PROJECT=<your-project-id>
```

Leave `CLIMATEKG_OLLAMA_URL` unset on native Linux so the app uses the Ollama
container. Start the stack from the repository root:

```bash
docker compose --env-file deployment/.env -f deployment/docker-compose.yml config --quiet
docker compose --env-file deployment/.env -f deployment/docker-compose.yml up -d --build
docker compose --env-file deployment/.env -f deployment/docker-compose.yml ps
```

First start downloads both models. Follow progress with
`docker compose --env-file deployment/.env -f deployment/docker-compose.yml logs -f ollama-models compute airflow-scheduler`.
The one-shot `airflow-init` and `ollama-models` containers should exit
successfully; the long-running services should remain up.

## 4. Verify End to End

```bash
curl --fail http://127.0.0.1:8780/api/config
curl --fail http://127.0.0.1:8080/health
docker compose --env-file deployment/.env -f deployment/docker-compose.yml exec ollama ollama list
```

`/api/config` should report `graph_ready`, `graphrag_ready`, and
`plain_rag_ready` as `true`. Submit a process query:

```bash
curl -sS -X POST http://127.0.0.1:8780/api/process-query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does surface heterogeneity affect local clouds under weak wind?","system":"climatekg"}'
```

Copy the returned `id` and poll
`http://127.0.0.1:8780/api/jobs/<id>` until `status` is `complete` or
`failed`. Check citations and the saved trace in
`/srv/climatekg/artifacts/queries/`. Then test a watershed in **Land use
planning** to verify Earth Engine enrichment. Access the app on
`http://127.0.0.1:8780/` locally or through an SSH tunnel.

For HTTPS, follow [`deployment/APACHE_DEPLOYMENT.md`](deployment/APACHE_DEPLOYMENT.md).
The current app has no public-user authentication. Add it before allowing
untrusted internet users to submit GPU jobs. See
[`deployment/OPERATIONS.md`](deployment/OPERATIONS.md) for troubleshooting.

## Validation Status

The Docker stack, Airflow, a cited process answer, and an Earth Engine-enriched
watershed answer were exercised on **Docker Desktop's Linux engine on
Windows**. That machine required native Windows Ollama because containerized
Ollama failed a CUDA allocation under WSL. Native Linux GPU inference, a
fresh Linux install, and HTTPS proxy deployment have **not yet been tested**.
Run the checks above on the target Linux server before claiming production
readiness. A completed query verifies execution, not scientific correctness.

The authoritative scientific specifications are
[`land_atmosphere_kg_indexing_pipeline.md`](land_atmosphere_kg_indexing_pipeline.md)
and [`land_atmosphere_kg_query_pipeline.md`](land_atmosphere_kg_query_pipeline.md).
