"""Durable job records and the Airflow-backed web job manager."""

from __future__ import annotations

import base64
import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp.answer_systems import ANSWER_SYSTEMS, DEFAULT_ANSWER_SYSTEM


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DurableJob:
    id: str
    kind: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    stages: list[dict[str, Any]] = field(default_factory=list)
    request: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    airflow_run_id: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stages": self.stages,
            "result": self.result,
            "error": self.error,
        }

    def stored(self) -> dict[str, Any]:
        return {**self.public(), "request": self.request, "airflow_run_id": self.airflow_run_id}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DurableJob":
        return cls(**{name: value.get(name) for name in cls.__dataclass_fields__ if name in value})


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def path(self, job_id: str) -> Path:
        if not job_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in job_id):
            raise ValueError("invalid job id")
        return self.root / f"{job_id}.json"

    def save(self, job: DurableJob) -> None:
        with self._lock:
            self._write(job)

    def _write(self, job: DurableJob) -> None:
        path = self.path(job.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(job.stored(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def load(self, job_id: str) -> DurableJob:
        path = self.path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        with self._lock:
            return DurableJob.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def update(self, job_id: str, **changes: Any) -> DurableJob:
        with self._lock:
            path = self.path(job_id)
            if not path.exists():
                raise KeyError(job_id)
            job = DurableJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for name, value in changes.items():
                if name not in DurableJob.__dataclass_fields__:
                    raise ValueError(f"unknown job field: {name}")
                setattr(job, name, value)
            job.updated_at = utc_now()
            self._write(job)
            return job

    def append_stage(self, job_id: str, name: str, details: dict[str, Any]) -> DurableJob:
        job = self.load(job_id)
        job.stages.append({"name": name, "details": details, "at": utc_now()})
        job.updated_at = utc_now()
        self.save(job)
        return job


def build_question(kind: str, payload: dict[str, Any], watersheds: Any) -> tuple[str, str | None]:
    if kind == "process":
        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("question is required")
        return question, None
    if kind != "planning":
        raise ValueError(f"unsupported job kind: {kind}")
    watershed_id = str(payload.get("watershed_id", "")).strip().upper()
    if not watersheds.contains(watershed_id):
        raise ValueError(f"unknown watershed: {watershed_id}")
    objective = str(payload.get("objective", "")).strip()
    if not objective:
        raise ValueError("planning objective is required")
    question = f"For watershed {watershed_id} in India, what land-use changes could {objective.rstrip('.?')}?"
    additional = str(payload.get("additional_information", "")).strip()
    if additional:
        question += f" Additional local information supplied by the user: {additional}"
    return question, watershed_id


class AirflowClient:
    def __init__(self, base_url: str, username: str, password: str, dag_id: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.dag_id = dag_id
        self.timeout = timeout

    def trigger(self, job_id: str) -> str:
        run_id = f"climatekg__{job_id}"
        body = {"dag_run_id": run_id, "conf": {"job_id": job_id}}
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/dags/{self.dag_id}/dagRuns",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Airflow rejected job {job_id}: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Airflow is unavailable at {self.base_url}: {exc.reason}") from exc
        return str(payload.get("dag_run_id") or run_id)


class AirflowJobManager:
    """Web-facing manager with the same submit/get contract as local JobManager."""

    def __init__(self, engine: Any, watersheds: Any, store: JobStore, client: AirflowClient) -> None:
        self.engine = engine
        self.watersheds = watersheds
        self.store = store
        self.client = client

    def submit(self, kind: str, payload: dict[str, Any]) -> DurableJob:
        question, watershed_id = build_question(kind, payload, self.watersheds)
        system = str(payload.get("system", "")).strip() or DEFAULT_ANSWER_SYSTEM
        if system not in {item["id"] for item in ANSWER_SYSTEMS}:
            raise ValueError(f"unsupported answer system: {system}")
        job = DurableJob(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            request={"question": question, "system": system, "watershed_id": watershed_id},
        )
        job.airflow_run_id = f"climatekg__{job.id}"
        self.store.save(job)
        try:
            run_id = self.client.trigger(job.id)
            if run_id != job.airflow_run_id:
                raise RuntimeError(f"unexpected Airflow run ID for job {job.id}: {run_id}")
        except Exception as exc:
            self.store.update(job.id, status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        return job

    def get(self, job_id: str) -> DurableJob:
        return self.store.load(job_id)


def manager_from_environment(engine: Any, watersheds: Any) -> AirflowJobManager:
    root = Path(os.environ.get("CLIMATEKG_JOB_ROOT", "/artifacts/jobs"))
    client = AirflowClient(
        os.environ.get("AIRFLOW_API_URL", "http://airflow-webserver:8080"),
        os.environ.get("AIRFLOW_API_USERNAME", "climatekg"),
        os.environ.get("AIRFLOW_API_PASSWORD", "change-me"),
        os.environ.get("AIRFLOW_DAG_ID", "climatekg_query"),
    )
    return AirflowJobManager(engine, watersheds, JobStore(root), client)
