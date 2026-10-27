# ClimateKG server deployment

This deployment runs the existing web frontend and query pipelines with Airflow
orchestration:

```text
browser -> backend -> Airflow -> computation service -> Airflow
        -> backend job record -> browser polling
```

The browser-facing API remains unchanged. Long computations are no longer tied
to an in-memory backend thread. Job requests, progress, results, and errors are
stored under the mounted artifacts directory.

## Documents

- `ARCHITECTURE.md` - services, request flow, and failure behavior.
- `INSTALLATION.md` - clean-server prerequisites and first installation.
- `DOCKER_DEPLOYMENT.md` - volumes, Compose commands, upgrades, and backups.
- `AIRFLOW_WORKFLOW.md` - DAG behavior and job-record contract.
- `APACHE_DEPLOYMENT.md` - HTTPS reverse proxy configuration.
- `OPERATIONS.md` - health checks, logs, retries, and troubleshooting.
- `IMPLEMENTATION_STATUS.md` - completed work, validation status, and the exact
  point from which deployment testing should resume.

The primary deployment path is Docker Compose. It keeps Airflow and Python
dependencies reproducible while mounting large indexes, Ollama models, and
generated artifacts from the host.

The clean integration branch and paused extraction experiment are documented
in `docs/INTEGRATION_BRANCH.md` and `docs/TEXT_FIRST_EXPERIMENT_STATUS.md`.
