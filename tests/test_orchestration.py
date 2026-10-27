from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from webapp.compute_service import ComputationRunner
from webapp.orchestration import AirflowJobManager, DurableJob, JobStore


@contextmanager
def job_directory():
    path = Path("webapp/.test_artifacts") / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeWatersheds:
    def contains(self, identifier: str) -> bool:
        return identifier == "W1"

    def feature(self, identifier: str):
        if identifier != "W1":
            raise KeyError(identifier)
        return {"properties": {"wsconc": "W1"}, "geometry": {"type": "Point", "coordinates": [77, 20]}}


class FakeAirflow:
    def __init__(self) -> None:
        self.triggered = []

    def trigger(self, job_id: str) -> str:
        self.triggered.append(job_id)
        return f"climatekg__{job_id}"


class FakeEngine:
    def run(self, question, query_id, system, stage_callback, planning_feature=None):
        stage_callback("query_parsed", {"mode": "global"})
        return {
            "query_id": query_id,
            "question": question,
            "system": system,
            "answer": "grounded",
            "planning_feature": planning_feature,
        }


def test_job_store_round_trip_and_rejects_path_traversal() -> None:
    with job_directory() as root:
        store = JobStore(root)
        expected = DurableJob(id="abc123", kind="process", request={"question": "test", "system": "climatekg"})
        store.save(expected)
        actual = store.load("abc123")
        assert actual.request == expected.request
        assert actual.status == "queued"
        with pytest.raises(ValueError):
            store.load("../secret")


def test_airflow_manager_persists_request_before_trigger() -> None:
    with job_directory() as root:
        airflow = FakeAirflow()
        manager = AirflowJobManager(FakeEngine(), FakeWatersheds(), JobStore(root), airflow)
        job = manager.submit("planning", {
            "watershed_id": "w1",
            "objective": "reduce heat",
            "additional_information": "Retain cropland.",
            "system": "climatekg",
        })
        stored = manager.get(job.id)
        assert airflow.triggered == [job.id]
        assert stored.airflow_run_id == f"climatekg__{job.id}"
        assert stored.request["watershed_id"] == "W1"
        assert "Retain cropland" in stored.request["question"]


def test_computation_runner_updates_durable_job_and_stages() -> None:
    with job_directory() as root:
        store = JobStore(root)
        store.save(DurableJob(
            id="job123",
            kind="process",
            request={"question": "How does irrigation affect heat?", "system": "climatekg", "watershed_id": None},
        ))
        runner = ComputationRunner(FakeEngine(), FakeWatersheds(), store)
        result = runner.run("job123")
        assert result["status"] == "complete"
        assert result["result"]["answer"] == "grounded"
        assert result["stages"][0]["name"] == "query_parsed"


def test_computation_runner_is_idempotent_after_completion() -> None:
    with job_directory() as root:
        store = JobStore(root)
        store.save(DurableJob(id="job123", kind="process", status="complete", result={"answer": "existing"}))
        runner = ComputationRunner(FakeEngine(), FakeWatersheds(), store)
        assert runner.run("job123")["result"]["answer"] == "existing"
