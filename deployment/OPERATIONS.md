# Operations and troubleshooting

## Health checks

```bash
docker compose ps
curl --fail http://127.0.0.1:8780/api/config
curl --fail http://127.0.0.1:8080/health
docker compose exec ollama ollama list
```

## Logs

```bash
docker compose logs --since 30m backend
docker compose logs --since 30m airflow-scheduler airflow-webserver
docker compose logs --since 30m compute ollama
```

Use the 12-character job ID to correlate the browser request, job JSON, Airflow
run (`climatekg__<job_id>`), computation logs, and query artifacts.

## Common failures

### Job stays queued

Check Airflow health, DAG import errors, API credentials, and scheduler logs. The
backend must be able to reach `airflow-webserver:8080`.

### Job stays running

Check the computation and Ollama logs. Confirm GPU memory is available. Do not
resubmit until determining whether inference is still active.

### Airflow reports 401

The values of `AIRFLOW_ADMIN_USERNAME` and `AIRFLOW_ADMIN_PASSWORD` used by the
backend must match the Airflow user created by `airflow-init`.

### Computation reports 401

`CLIMATEKG_INTERNAL_TOKEN` must have the same non-empty value in Airflow and the
application services. Restart affected containers after changing it.

### Graph or baseline not ready

Verify the `CLIMATEKG_DATA_DIR` layout and read permissions. Check for
`parquet_graph/manifest.json`, GraphRAG Parquet files, and the Plain RAG index.

### Earth Engine enrichment fails

Verify `EARTH_ENGINE_PROJECT`, the mounted credential file, service-account
permissions, and dataset access. The pipeline intentionally does not substitute
local environmental values when Earth Engine fails.

## Capacity

The default stack runs one query at a time. Increase concurrency only after
measuring GPU memory, model context size, graph memory, and Earth Engine quotas.
Changing Airflow concurrency alone is insufficient because the computation
service also serializes inference.
