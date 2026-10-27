# Docker and Airflow integration branch

Branch: `integration/airflow-docker-v1`.

This branch starts from committed KG revision `4a60027`, then integrates the
web app and deployment code. It does **not** merge the paused text-first Claim
experiment. The scientific 30-paper expansion gate from the atomic evidence
experiment was not passed; this branch is a runnable integration candidate, not
a claim of validated scientific superiority.

## Runtime layout

- Application code lives in the image.
- `/data` is a read-only mounted Parquet KG and baseline indexes.
- `/app/assets` is a read-only mount of the watershed GeoJSON and Koppen KMZ.
- `/root/.ollama` is a mounted Ollama model store.
- `/artifacts/jobs` and `/artifacts/queries` persist job and query traces.
- `/credentials` is a read-only mount for Earth Engine credentials.

The sample 115-paper index resides outside Git in
`climatekg/runtime/outputs/three_system_benchmark`. It contains 1,724 Claims
and indexes for ClimateKG, Microsoft GraphRAG and Plain RAG. It was built before
this integration branch; its scientific contents are unchanged here.

The browser submits a job to the backend. The backend triggers an Airflow DAG.
Airflow calls a private computation service; the result and progress are written
to mounted job records. The browser polls the backend for completion. Airflow
and computation ports are not exposed publicly. The backend and Airflow UI bind
to localhost; use Apache or another HTTPS proxy for external access.

## Local Windows demo

This worktree's ignored `deployment/.env` points to the original workspace's
indexes and assets, the existing Ollama model store, and a persistent artifact
directory. It contains local generated credentials and must never be committed.

```powershell
docker compose --env-file deployment/.env -f deployment/docker-compose.yml config --quiet
docker compose --env-file deployment/.env -f deployment/docker-compose.yml build backend compute
docker compose --env-file deployment/.env -f deployment/docker-compose.yml up -d
docker compose --env-file deployment/.env -f deployment/docker-compose.yml ps
```

Web app: `http://127.0.0.1:8780/`.
Airflow operator UI: `http://127.0.0.1:8080/`.

Server installation and Apache setup are in `deployment/INSTALLATION.md` and
`deployment/APACHE_DEPLOYMENT.md`. Supply real mounted data and model paths;
an empty mount is an error, not a fallback to invented data. Watershed planning
also requires valid Earth Engine application-default credentials for project
`ee-atharv` or the deployment's configured project.

## Integration checks

- Existing semantic State links remain loaded by the web application.
- Synthesis-selected Claims remain in the compact API report even when not in
  its top-eight candidate preview.
- Query traces use the mounted `/artifacts/queries` path.
- Complete Python test suite: 141 passed with an existing local tokenizer cache.
- Focused integration tests: 21 passed after preserving semantic links and
  synthesis-selected Claim visibility.
- Docker Compose configuration passed. Image build and live flow status are
  recorded in `deployment/IMPLEMENTATION_STATUS.md`.

The web application was also started without Docker on port 8781 to check the
HTTP interface against the mounted-equivalent local paths. This is not a
substitute for the pending Airflow/Docker end-to-end check.
A local GraphRAG job completed and saved a cited trace. Its answer still needs
scientific review; see the concrete terminology error in
`deployment/IMPLEMENTATION_STATUS.md`.
