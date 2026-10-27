# Airflow workflow

## DAG

The `climatekg_query` DAG has one task, `run_query`. It reads `job_id` from DAG
run configuration and calls the private computation service. The DAG is not
scheduled; every run is triggered by the application backend.

Example DAG configuration:

```json
{"job_id": "a1b2c3d4e5f6"}
```

`max_active_runs=1` protects the default single-GPU deployment. The task retries
once after 30 seconds. The computation service independently prevents concurrent
inference inside its process.

## Job record

Job files are stored as `/artifacts/jobs/<job_id>.json`:

```json
{
  "id": "a1b2c3d4e5f6",
  "kind": "process",
  "status": "queued",
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "stages": [],
  "request": {
    "question": "How does irrigation affect heat?",
    "system": "climatekg",
    "watershed_id": null
  },
  "result": null,
  "error": null,
  "airflow_run_id": "climatekg__a1b2c3d4e5f6"
}
```

The public API never returns the stored `request` or Airflow run ID. It returns
the question inside the completed result, as before.

## States

```text
queued -> running -> complete
                  -> failed
```

Malformed requests fail before DAG creation. Airflow trigger failures are saved
as `failed` and returned as HTTP 503. Computation exceptions are saved by the
computation service. The DAG failure callback records failures that happen before
the computation service can update the job.

## Retrying a job

Airflow performs its configured automatic retry. Before a manual retry, inspect
the job file and computation logs. Do not clear and rerun a task whose job is
still actively `running`. For an explicitly failed job, create a new submission
so its identity and trace remain unambiguous.

## Airflow UI

The UI binds to `127.0.0.1:8080` and is intended for operators only. Access it
through an SSH tunnel when remote administration is required:

```bash
ssh -L 8080:127.0.0.1:8080 user@server
```

Do not proxy the Airflow UI through the public ClimateKG virtual host.
