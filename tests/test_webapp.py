from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from webapp.server import JobManager, WatershedCatalog, create_server


@contextmanager
def workspace_test_dir() -> Iterator[Path]:
    path = Path("webapp") / ".test_artifacts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeEngine:
    model = "qwen3.6:27b"

    def config(self) -> dict:
        return {
            "answer_systems": [
                {"id": "graphrag", "label": "Microsoft GraphRAG"},
                {"id": "plain_rag", "label": "Plain RAG"},
                {"id": "climatekg", "label": "ClimateKG (context-aware)"},
            ],
            "default_system": "graphrag",
            "generation_model": self.model,
            "graph_ready": True,
            "graphrag_ready": True,
            "plain_rag_ready": True,
            "corpus": {"papers": 2},
        }

    def run(self, question, query_id, system, stage_callback, planning_feature=None):
        stage_callback("query_parsed", {"mode": "forward"})
        return {"query_id": query_id, "system": system, "question": question, "answer": "Grounded test answer"}


def write_watersheds(path: Path) -> None:
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"wsconc": "C07BRA20", "area_sqkm": 10.5, "bacode": "07", "sbcode": "BRA"},
            "geometry": {"type": "Polygon", "coordinates": [[[77, 20], [78, 20], [78, 21], [77, 20]]]},
        }],
    }), encoding="utf-8")


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def test_planning_question_retains_selected_watershed_and_user_information() -> None:
    with workspace_test_dir() as test_dir:
        watershed_path = test_dir / "watersheds.geojson"
        write_watersheds(watershed_path)
        manager = JobManager(FakeEngine(), WatershedCatalog(watershed_path), test_dir / "jobs")

        question = manager._question("planning", {
            "watershed_id": "c07bra20",
            "objective": "reduce local heat",
            "additional_information": "Rainfed cropland; focus on pre-monsoon months.",
        })

        assert "watershed C07BRA20" in question
        assert "reduce local heat" in question
        assert "Rainfed cropland" in question


def test_webapp_api_runs_process_job_and_serves_watersheds() -> None:
    with workspace_test_dir() as test_dir:
        watershed_path = test_dir / "watersheds.geojson"
        write_watersheds(watershed_path)
        manager = JobManager(FakeEngine(), WatershedCatalog(watershed_path), test_dir / "jobs")
        server = create_server("127.0.0.1", 0, manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(f"{base}/api/config", timeout=5) as response:
                config = json.load(response)
            with urllib.request.urlopen(f"{base}/api/watersheds", timeout=5) as response:
                watersheds = json.load(response)
            job = post_json(f"{base}/api/process-query", {
                "question": "How does irrigation affect heat?",
                "system": "graphrag",
            })
            for _ in range(20):
                with urllib.request.urlopen(f"{base}/api/jobs/{job['id']}", timeout=5) as response:
                    final = json.load(response)
                if final["status"] in {"complete", "failed"}:
                    break
            assert config["watersheds"]["count"] == 1
            assert config["default_system"] == "graphrag"
            assert watersheds["features"][0]["properties"]["wsconc"] == "C07BRA20"
            assert final["status"] == "complete"
            assert final["result"]["answer"] == "Grounded test answer"
            assert final["stages"][0]["name"] == "query_parsed"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def test_webapp_rejects_unknown_answer_system() -> None:
    with workspace_test_dir() as test_dir:
        watershed_path = test_dir / "watersheds.geojson"
        write_watersheds(watershed_path)
        manager = JobManager(FakeEngine(), WatershedCatalog(watershed_path), test_dir / "jobs")
        server = create_server("127.0.0.1", 0, manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/process-query",
                data=json.dumps({"question": "test", "system": "unconfigured"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(request, timeout=5)
                raise AssertionError("request should fail")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def test_watershed_context_cards_have_explanation_dialog() -> None:
    html = Path("webapp/index.html").read_text(encoding="utf-8")
    javascript = Path("webapp/js/app.js").read_text(encoding="utf-8")

    assert 'id="facet-dialog"' in html
    assert 'data-facet-index="${index}"' in javascript
    assert "Why it matters here" in javascript
    assert "Data provenance" in javascript
    assert "source.dataset" in javascript


def test_webapp_lists_real_answer_systems_with_graphrag_default() -> None:
    html = Path("webapp/index.html").read_text(encoding="utf-8")
    javascript = Path("webapp/js/app.js").read_text(encoding="utf-8")

    assert 'id="process-system"' in html
    assert 'id="planning-system"' in html
    assert "config.answer_systems" in javascript
    assert "config.default_system" in javascript
