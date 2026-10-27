# Installation on a clean server

These instructions target Ubuntu 24.04 with an NVIDIA GPU. CPU-only execution is
possible but Qwen3.6-27B latency will generally be unsuitable for the web demo.

## Software and library inventory

The application image uses Python 3.13 and installs the repository with the
`baselines` optional dependency group. The principal Python libraries are:

- Pydantic 2.x for schemas and validation;
- PyArrow for Parquet graph tables;
- NumPy and FAISS CPU for deterministic scoring and ANN retrieval;
- pandas and graspologic-native for the adapted GraphRAG index;
- tiktoken for prompt/token accounting;
- Earth Engine API, Rasterio, and Pillow for spatial enrichment;
- Python standard-library HTTP servers for the public and internal APIs.

The application container additionally installs `curl` for health checks and
`libgomp1` for FAISS/OpenMP runtime support. Airflow runs in its separate pinned
Python 3.12 image and PostgreSQL 16 stores Airflow metadata. Ollama and its CUDA
runtime are isolated in the Ollama container.

For a native application environment, install from the repository root:

```bash
python3.13 -m venv .venv-climatekg
.venv-climatekg/bin/python -m pip install --upgrade pip setuptools wheel
.venv-climatekg/bin/python -m pip install -e '.[baselines]'
```

## 1. Install host software

Install:

- Git;
- Docker Engine and the Docker Compose plugin;
- NVIDIA driver compatible with the installed GPU;
- NVIDIA Container Toolkit;
- Apache 2.4 and Certbot when HTTPS is required.

Verify GPU container access:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
docker compose version
```

## 2. Clone the repository

```bash
sudo mkdir -p /opt/climatekg
sudo chown "$USER":"$USER" /opt/climatekg
git clone <repository-url> /opt/climatekg/app
cd /opt/climatekg/app/deployment
```

## 3. Prepare mounted directories

```bash
sudo mkdir -p /srv/climatekg/{data,models,artifacts,credentials}
sudo chgrp -R 0 /srv/climatekg/artifacts
sudo chmod -R 2770 /srv/climatekg/artifacts
```

The data directory must have this structure:

```text
/srv/climatekg/data/
├── parquet_graph/
│   ├── manifest.json
│   ├── *.parquet
│   └── ann/
└── baselines/
    ├── graphrag/
    └── plain_rag/index/
```

Copy `watershed_pan_india_simplified.geojson` and the Koppen KMZ into the
configured `CLIMATEKG_ASSETS_DIR` directory. These files are mounted read-only.

For watershed enrichment, place Earth Engine application-default credentials at:

```text
/srv/climatekg/credentials/application_default_credentials.json
```

Use a dedicated service identity for a server. Do not copy a personal credential
file into the Git repository or Docker image.

## 4. Configure deployment

```bash
cp .env.example .env
openssl rand -hex 32
```

Edit `.env` and set:

```dotenv
CLIMATEKG_INTERNAL_TOKEN=<generated-token>
AIRFLOW_ADMIN_PASSWORD=<strong-password>
CLIMATEKG_DATA_DIR=/srv/climatekg/data
CLIMATEKG_ASSETS_DIR=/srv/climatekg/assets
CLIMATEKG_MODELS_DIR=/srv/climatekg/models
CLIMATEKG_ARTIFACTS_DIR=/srv/climatekg/artifacts
CLIMATEKG_CREDENTIALS_DIR=/srv/climatekg/credentials
EARTH_ENGINE_PROJECT=ee-your-project
```

## 5. Build and start

```bash
docker compose config
docker compose build backend compute
docker compose up airflow-init
docker compose up -d
docker compose ps
```

The first startup pulls `qwen3.6:27b` and `qwen3-embedding:4b` into the mounted
model directory. This can take considerable time. Subsequent starts reuse them.

## 6. Verify

```bash
curl --fail http://127.0.0.1:8780/api/config
curl --fail http://127.0.0.1:8080/health

curl -sS -X POST http://127.0.0.1:8780/api/process-query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does irrigation affect near-surface heat?","system":"climatekg"}'
```

Use the returned job ID:

```bash
curl --fail http://127.0.0.1:8780/api/jobs/<job-id>
```

After this works locally, configure Apache using `APACHE_DEPLOYMENT.md`.

## Native development installation

For code development without containers, use Python 3.13 for ClimateKG and a
separate Python 3.12 environment for Airflow 2.10.5. Run Ollama separately, set
`CLIMATEKG_JOB_BACKEND=local` to retain the existing in-process job mode, and
start the webapp with:

```bash
python -m webapp.server --host 127.0.0.1 --port 8780
```

The Airflow-backed Docker deployment is the supported server configuration.
