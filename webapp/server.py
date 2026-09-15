from __future__ import annotations

import argparse
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from climatekg.config import OUTPUT_ROOT, PIPELINE, QUERY_PIPELINE
from climatekg.parquet_graph import ParquetGraph
from climatekg.query import run_query
from climatekg.utils import write_json


WEBAPP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBAPP_DIR.parent
WATERSHED_PATH = PROJECT_ROOT / "assets" / "watershed_pan_india_simplified.geojson"
KOPPEN_PATH = PROJECT_ROOT / "assets" / "Global_1986-2010_KG_5m.kmz.zip"
DEFAULT_GRAPH_ROOT = OUTPUT_ROOT / "three_system_benchmark" / "parquet_graph"
WEBAPP_OUTPUT_ROOT = PROJECT_ROOT / "climatekg" / "runtime" / "webapp" / "queries"
TIKTOKEN_CACHE_ROOT = PROJECT_ROOT / "climatekg" / "runtime" / "cache" / "tiktoken"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(TIKTOKEN_CACHE_ROOT))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class WatershedCatalog:
    def __init__(self, path: Path = WATERSHED_PATH) -> None:
        self.path = path.resolve()
        self._features: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._features is None:
            payload = read_json(self.path)
            if payload.get("type") != "FeatureCollection":
                raise ValueError("watershed file must be a GeoJSON FeatureCollection")
            features: dict[str, dict[str, Any]] = {}
            for feature in payload.get("features", []):
                watershed_id = str(feature.get("properties", {}).get("wsconc", "")).strip()
                if watershed_id:
                    features[watershed_id] = feature
            self._features = features
        return self._features

    def contains(self, watershed_id: str) -> bool:
        return watershed_id in self._load()

    def summary(self, watershed_id: str) -> dict[str, Any]:
        feature = self._load()[watershed_id]
        properties = feature["properties"]
        return {
            "id": watershed_id,
            "area_sqkm": properties.get("area_sqkm"),
            "basin_code": properties.get("bacode"),
            "subbasin_code": properties.get("sbcode"),
        }

    @property
    def count(self) -> int:
        return len(self._load())


class ClimateKGEngine:
    def __init__(
        self,
        graph_root: Path = DEFAULT_GRAPH_ROOT,
        output_root: Path = WEBAPP_OUTPUT_ROOT,
        watershed_path: Path = WATERSHED_PATH,
    ) -> None:
        self.graph_root = graph_root.resolve()
        self.output_root = output_root.resolve()
        self.watershed_path = watershed_path.resolve()
        self.koppen_path = KOPPEN_PATH.resolve()
        self.model = QUERY_PIPELINE["ollama"]["model"]
        self._papers = None
        self._indexes = None
        self._load_lock = threading.Lock()

        # Browser selection supplies a registry identifier, so the query pipeline
        # must resolve it against the same GeoJSON displayed on the map.
        PIPELINE["enrichment"]["watershed_registry_path"] = str(self.watershed_path)
        PIPELINE["enrichment"]["datasets"]["climate_regime"]["source_path"] = str(self.koppen_path)

    def config(self) -> dict[str, Any]:
        manifest_path = self.graph_root / "manifest.json"
        table_counts = read_json(manifest_path).get("tables", {}) if manifest_path.exists() else {}
        return {
            "generation_models": [self.model],
            "default_model": self.model,
            "graph_ready": manifest_path.exists(),
            "graph_root": str(self.graph_root),
            "corpus": table_counts,
            "koppen_ready": self.koppen_path.is_file(),
        }

    def _load_graph(self) -> None:
        if self._papers is not None:
            return
        with self._load_lock:
            if self._papers is None:
                if not (self.graph_root / "manifest.json").exists():
                    raise FileNotFoundError(f"Parquet graph not found: {self.graph_root}")
                graph = ParquetGraph(self.graph_root)
                self._papers = graph.read_corpus()
                self._indexes = graph.read_indexes()

    def run(
        self,
        question: str,
        query_id: str,
        model: str,
        stage_callback: Callable[[str, dict[str, Any]], None],
    ) -> dict[str, Any]:
        if model != self.model:
            raise ValueError(f"unsupported model: {model}")
        self._load_graph()
        report = run_query(
            question,
            query_id,
            self._papers,
            self.output_root,
            stage_callback=stage_callback,
            indexes=self._indexes,
        )
        return compact_report(report, self.output_root / query_id)


def compact_report(report: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    spec = report.get("query_spec", {})
    facets = spec.get("context", {}).get("facets", [])
    return {
        "query_id": report["query_id"],
        "answer": report.get("answer", ""),
        "mode": spec.get("mode"),
        "question": spec.get("user_question"),
        "spatial_support": spec.get("context", {}).get("spatial_support"),
        "user_facets": [item for item in facets if item.get("origin") == "user"],
        "derived_facets": [item for item in facets if item.get("origin") == "derived"],
        "contexts": report.get("context_candidates", [])[:5],
        "claims": report.get("claim_candidates", [])[:8],
        "paths": report.get("paths", [])[:5],
        "provenance": report.get("synthesis", {}).get("provenance", {}),
        "warnings": report.get("warnings", []),
        "artifact_dir": str(artifact_dir),
    }


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    stages: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None

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


class JobManager:
    def __init__(self, engine: ClimateKGEngine, watersheds: WatershedCatalog, job_root: Path | None = None) -> None:
        self.engine = engine
        self.watersheds = watersheds
        self.jobs: dict[str, Job] = {}
        self.job_root = job_root or engine.output_root.parent / "jobs"
        self._jobs_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def submit(self, kind: str, payload: dict[str, Any]) -> Job:
        question = self._question(kind, payload)
        model = str(payload.get("model", "")).strip() or self.engine.model
        if model != self.engine.model:
            raise ValueError(f"unsupported model: {model}")
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        with self._jobs_lock:
            self.jobs[job.id] = job
            self._persist(job)
        threading.Thread(
            target=self._execute,
            args=(job, question, model),
            daemon=True,
            name=f"climatekg-{job.id}",
        ).start()
        return job

    def get(self, job_id: str) -> Job:
        with self._jobs_lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return self.jobs[job_id]

    def _question(self, kind: str, payload: dict[str, Any]) -> str:
        if kind == "process":
            question = str(payload.get("question", "")).strip()
            if not question:
                raise ValueError("question is required")
            return question
        if kind != "planning":
            raise ValueError(f"unsupported job kind: {kind}")
        watershed_id = str(payload.get("watershed_id", "")).strip().upper()
        if not self.watersheds.contains(watershed_id):
            raise ValueError(f"unknown watershed: {watershed_id}")
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("planning objective is required")
        question = f"For watershed {watershed_id} in India, what land-use changes could {objective.rstrip('.?')}?"
        additional = str(payload.get("additional_information", "")).strip()
        if additional:
            question += f" Additional local information supplied by the user: {additional}"
        return question

    def _execute(self, job: Job, question: str, model: str) -> None:
        def update(stage: str, details: dict[str, Any]) -> None:
            with self._jobs_lock:
                job.stages.append({"name": stage, "details": details, "at": utc_now()})
                job.updated_at = utc_now()
                self._persist(job)

        try:
            with self._jobs_lock:
                job.status = "running"
                job.updated_at = utc_now()
                self._persist(job)
            with self._inference_lock:
                query_id = f"WEB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job.id[:6]}"
                result = self.engine.run(question, query_id, model, update)
            with self._jobs_lock:
                job.result = result
                job.status = "complete"
                job.updated_at = utc_now()
                self._persist(job)
        except Exception as exc:
            with self._jobs_lock:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.updated_at = utc_now()
                self._persist(job)

    def _persist(self, job: Job) -> None:
        write_json(self.job_root / f"{job.id}.json", job.public())


class WebAppHandler(SimpleHTTPRequestHandler):
    manager: JobManager

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEBAPP_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[webapp] {self.address_string()} {format % args}")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _request_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 65_536:
            raise ValueError("request body must be between 1 byte and 64 KiB")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/config":
                config = self.manager.engine.config()
                config["watersheds"] = {
                    "ready": self.manager.watersheds.path.exists(),
                    "count": self.manager.watersheds.count,
                }
                self._json(config)
                return
            if path == "/api/watersheds":
                self._serve_file(self.manager.watersheds.path, "application/geo+json")
                return
            if path.startswith("/api/jobs/"):
                self._json(self.manager.get(path.removeprefix("/api/jobs/")).public())
                return
        except KeyError:
            self._json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
            return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        routes = {"/api/process-query": "process", "/api/land-use-plan": "planning"}
        if path not in routes:
            self._json({"error": "endpoint not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            job = self.manager.submit(routes[path], self._request_json())
            self._json(job.public(), HTTPStatus.ACCEPTED)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _serve_file(self, path: Path, content_type: str) -> None:
        size = path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)


def create_server(
    host: str,
    port: int,
    manager: JobManager | None = None,
) -> ThreadingHTTPServer:
    if manager is None:
        graph_root = Path(os.environ.get("CLIMATEKG_WEBAPP_GRAPH_ROOT", DEFAULT_GRAPH_ROOT))
        engine = ClimateKGEngine(graph_root=graph_root)
        manager = JobManager(engine, WatershedCatalog())
    handler = type("ConfiguredWebAppHandler", (WebAppHandler,), {"manager": manager})
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ClimateKG prototype web application.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8780, type=int)
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"ClimateKG prototype: http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
