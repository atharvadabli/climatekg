"""Airflow DAG for one durable ClimateKG query job."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from airflow import DAG
from airflow.operators.python import PythonOperator


JOB_ROOT = Path(os.environ.get("CLIMATEKG_JOB_ROOT", "/artifacts/jobs"))
COMPUTE_URL = os.environ.get("CLIMATEKG_COMPUTE_URL", "http://compute:8790").rstrip("/")
INTERNAL_TOKEN = os.environ.get("CLIMATEKG_INTERNAL_TOKEN", "")


def _job_id(context: dict[str, Any]) -> str:
    value = str((context["dag_run"].conf or {}).get("job_id", ""))
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in value):
        raise ValueError("DAG conf must contain a valid job_id")
    return value


def _mark_failed(context: dict[str, Any]) -> None:
    try:
        job_id = _job_id(context)
        path = JOB_ROOT / f"{job_id}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("status") in {"complete", "failed"}:
            return
        exception = context.get("exception")
        value.update({
            "status": "failed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": f"Airflow task failed: {exception}",
        })
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except Exception as exc:
        print(f"Could not record Airflow failure: {exc}")


def run_computation(**context: Any) -> None:
    if not INTERNAL_TOKEN:
        raise RuntimeError("CLIMATEKG_INTERNAL_TOKEN is empty")
    job_id = _job_id(context)
    request = urllib.request.Request(
        f"{COMPUTE_URL}/internal/jobs/{job_id}/run",
        data=b"{}",
        headers={"Authorization": f"Bearer {INTERNAL_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=7200) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"computation service returned HTTP {exc.code}: {detail}") from exc
    if result.get("status") != "complete":
        raise RuntimeError(f"computation ended with status {result.get('status')}: {result.get('error')}")


with DAG(
    dag_id="climatekg_query",
    description="Run one ClimateKG, GraphRAG, or Plain RAG query",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    default_args={"owner": "climatekg", "retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["climatekg", "query"],
) as dag:
    PythonOperator(
        task_id="run_query",
        python_callable=run_computation,
        on_failure_callback=_mark_failed,
    )
