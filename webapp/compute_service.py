"""Internal persistent computation service invoked by Airflow."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from webapp.orchestration import JobStore
from webapp.server import ClimateKGEngine, DEFAULT_GRAPH_ROOT, WATERSHED_PATH, WatershedCatalog


class ComputationRunner:
    def __init__(self, engine: ClimateKGEngine, watersheds: WatershedCatalog, store: JobStore) -> None:
        self.engine = engine
        self.watersheds = watersheds
        self.store = store
        self._inference_lock = threading.Lock()

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.store.load(job_id)
        if job.status == "complete":
            return job.public()
        if job.status == "running":
            raise RuntimeError(f"job is already running: {job_id}")
        request = job.request
        question = str(request.get("question", "")).strip()
        system = str(request.get("system", "")).strip()
        if not question or not system:
            raise ValueError("stored job request is incomplete")
        watershed_id = request.get("watershed_id")
        planning_feature = self.watersheds.feature(str(watershed_id)) if watershed_id else None

        self.store.update(job_id, status="running", error=None)

        def stage(name: str, details: dict[str, Any]) -> None:
            self.store.append_stage(job_id, name, details)

        try:
            with self._inference_lock:
                query_id = f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job_id[:6]}"
                result = self.engine.run(question, query_id, system, stage, planning_feature)
            return self.store.update(job_id, status="complete", result=result, error=None).public()
        except Exception as exc:
            self.store.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            raise


class ComputationHandler(BaseHTTPRequestHandler):
    runner: ComputationRunner
    token: str

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[compute] {self.address_string()} {format % args}")

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.token}"
        return bool(self.token) and hmac.compare_digest(supplied, expected)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self._json({"status": "ok"})
            return
        self._json({"error": "endpoint not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            self._json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        path = unquote(urlparse(self.path).path)
        prefix, suffix = "/internal/jobs/", "/run"
        if not path.startswith(prefix) or not path.endswith(suffix):
            self._json({"error": "endpoint not found"}, HTTPStatus.NOT_FOUND)
            return
        job_id = path[len(prefix):-len(suffix)]
        try:
            self._json(self.runner.run(job_id))
        except KeyError:
            self._json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, RuntimeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def create_compute_server(host: str, port: int, runner: ComputationRunner, token: str) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("CLIMATEKG_INTERNAL_TOKEN must not be empty")
    handler = type("ConfiguredComputationHandler", (ComputationHandler,), {"runner": runner, "token": token})
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the internal ClimateKG computation service.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    graph_root = Path(os.environ.get("CLIMATEKG_WEBAPP_GRAPH_ROOT", DEFAULT_GRAPH_ROOT))
    watershed_path = Path(os.environ.get("CLIMATEKG_WATERSHED_PATH", WATERSHED_PATH))
    job_root = Path(os.environ.get("CLIMATEKG_JOB_ROOT", "/artifacts/jobs"))
    engine = ClimateKGEngine(graph_root=graph_root, ollama_url=os.environ.get("OLLAMA_URL"))
    runner = ComputationRunner(engine, WatershedCatalog(watershed_path), JobStore(job_root))
    server = create_compute_server(args.host, args.port, runner, os.environ.get("CLIMATEKG_INTERNAL_TOKEN", ""))
    print(f"ClimateKG computation service: http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
