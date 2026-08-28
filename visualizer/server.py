from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


VISUALIZER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = VISUALIZER_DIR.parent
DEFAULT_PAPER_ROOT = PROJECT_ROOT / "climatekg" / "runtime" / "data" / "papers"
DEFAULT_PROMPT_EXAMPLE_ROOT = PROJECT_ROOT / "climatekg" / "runtime" / "prompt_examples"
DEFAULT_QUERY_ROOT = PROJECT_ROOT / "climatekg" / "runtime" / "outputs"


def without_embeddings(value: Any) -> Any:
    """Remove high-volume vectors while preserving scientific and trace data."""
    if isinstance(value, dict):
        return {
            key: without_embeddings(item)
            for key, item in value.items()
            if "embedding" not in key.lower()
        }
    if isinstance(value, list):
        return [without_embeddings(item) for item in value]
    return value


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def clean_title(title: str) -> str:
    return title.lstrip("# ").strip() or "Untitled paper"


def read_prefix(path: Path, limit: int = 524_288) -> str:
    with path.open(encoding="utf-8") as handle:
        return handle.read(limit)


def object_from_prefix(text: str, key: str) -> dict[str, Any]:
    marker = f'"{key}"'
    key_start = text.find(marker)
    if key_start < 0:
        raise KeyError(key)
    value_start = text.find(":", key_start + len(marker)) + 1
    value, _ = json.JSONDecoder().raw_decode(text[value_start:].lstrip())
    if not isinstance(value, dict):
        raise TypeError(f"{key} is not an object")
    return value


def string_from_prefix(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*("(?:\\.|[^"\\])*")', text)
    return json.loads(match.group(1)) if match else None


@dataclass(frozen=True)
class PaperArtifact:
    artifact_id: str
    paper_id: str
    path: Path
    summary: dict[str, Any]


@dataclass(frozen=True)
class QueryArtifact:
    trace_id: str
    path: Path
    summary: dict[str, Any]


class ArtifactStore:
    def __init__(self, paper_root: Path = DEFAULT_PAPER_ROOT, query_root: Path = DEFAULT_QUERY_ROOT, additional_paper_roots: list[Path] | None = None) -> None:
        self.paper_root = paper_root.resolve()
        self.query_root = query_root.resolve()
        if additional_paper_roots is None and self.paper_root == DEFAULT_PAPER_ROOT.resolve():
            additional_paper_roots = [DEFAULT_PROMPT_EXAMPLE_ROOT]
        self.additional_paper_roots = [root.resolve() for root in (additional_paper_roots or [])]
        self._paper_artifacts: dict[str, PaperArtifact] = {}
        self._query_artifacts: dict[str, QueryArtifact] = {}
        self.refresh()

    def refresh(self) -> None:
        self._paper_artifacts = self._scan_papers()
        self._query_artifacts = self._scan_queries()

    def _scan_papers(self) -> dict[str, PaperArtifact]:
        artifacts: dict[str, PaperArtifact] = {}
        candidates = list(self.paper_root.glob("P*/final/final_paper.json")) if self.paper_root.exists() else []
        for root in self.additional_paper_roots:
            if root.exists():
                candidates.extend(root.rglob("final/final_paper.json"))
        for path in sorted(set(candidates)):
            try:
                paper = object_from_prefix(read_prefix(path, 65_536), "paper")
                paper_id = str(paper["id"])
                paper_manifest_path = path.parent.parent / "manifest.json"
                paper_manifest = read_json(paper_manifest_path) if paper_manifest_path.exists() else {}
                counts = paper_manifest.get("counts") or {}
                artifact_id = paper_id
                if artifact_id in artifacts:
                    example_name = next((part for part in path.parts if part.startswith("atsc-")), None)
                    example_name = example_name or next((part for part in path.parts if part.startswith("prompt_")), path.parent.parent.name)
                    version = next((part for part in path.parts if re.fullmatch(r"v\d+", part)), "artifact")
                    artifact_id = f"{paper_id}--{example_name}--{version}"
                summary = {
                    "artifact_id": artifact_id,
                    "id": paper_id,
                    "title": clean_title(str(paper.get("title", ""))),
                    "year": paper.get("year"),
                    "doi": paper.get("doi"),
                    "source_file": paper.get("source_file"),
                    "counts": {key: int(counts.get(key, 0)) for key in ("contexts", "facets", "transitions", "claims", "states", "source_blocks")},
                    "updated_at": path.stat().st_mtime,
                    "artifact_source": "prompt_example" if DEFAULT_PROMPT_EXAMPLE_ROOT.resolve() in path.parents else "indexed_paper",
                }
                artifacts[artifact_id] = PaperArtifact(artifact_id, paper_id, path, summary)
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return artifacts

    def _scan_queries(self) -> dict[str, QueryArtifact]:
        artifacts: dict[str, QueryArtifact] = {}
        if not self.query_root.exists():
            return artifacts
        paths = sorted(self.query_root.rglob("query_report.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for index, path in enumerate(paths, start=1):
            try:
                prefix = read_prefix(path)
                query_id = string_from_prefix(prefix, "query_id") or path.parent.name
                run_id = next((part for part in path.parts if part.startswith("query-suite-")), path.parent.parent.name)
                trace_id = f"QT{index:04d}"
                summary = {
                    "trace_id": trace_id,
                    "query_id": query_id,
                    "run_id": run_id,
                    "question": string_from_prefix(prefix, "user_question") or query_id,
                    "mode": string_from_prefix(prefix, "mode"),
                    "counts": {
                        "contexts": None,
                        "claims": None,
                        "paths": None,
                        "warnings": None,
                    },
                    "updated_at": path.stat().st_mtime,
                }
                artifacts[trace_id] = QueryArtifact(trace_id, path, summary)
            except (OSError, TypeError, json.JSONDecodeError):
                continue
        return artifacts

    def manifest(self) -> dict[str, Any]:
        papers = [artifact.summary for artifact in self._paper_artifacts.values()]
        queries = [artifact.summary for artifact in self._query_artifacts.values()]
        totals = {
            key: sum(paper["counts"].get(key, 0) for paper in papers)
            for key in ("contexts", "facets", "transitions", "claims", "states", "source_blocks")
        }
        return {"papers": papers, "queries": queries, "totals": totals}

    def paper(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._paper_artifacts.get(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        return without_embeddings(read_json(artifact.path))

    def query(self, trace_id: str) -> dict[str, Any]:
        artifact = self._query_artifacts.get(trace_id)
        if artifact is None:
            raise KeyError(trace_id)
        return without_embeddings(read_json(artifact.path))


class VisualizerHandler(SimpleHTTPRequestHandler):
    store: ArtifactStore

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(VISUALIZER_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[visualizer] {self.address_string()} {format % args}")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/manifest":
                self._json(self.store.manifest())
                return
            if path == "/api/refresh":
                self.store.refresh()
                self._json(self.store.manifest())
                return
            if path.startswith("/api/papers/"):
                self._json(self.store.paper(path.removeprefix("/api/papers/")))
                return
            if path.startswith("/api/queries/"):
                self._json(self.store.query(path.removeprefix("/api/queries/")))
                return
        except KeyError:
            self._json({"error": "Artifact not found"}, HTTPStatus.NOT_FOUND)
            return
        except (OSError, json.JSONDecodeError) as exc:
            self._json({"error": f"Could not read artifact: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()


def create_server(host: str, port: int, store: ArtifactStore | None = None) -> ThreadingHTTPServer:
    VisualizerHandler.store = store or ArtifactStore()
    return ThreadingHTTPServer((host, port), VisualizerHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore ClimateKG artifacts in a local web application.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--open", action="store_true", help="Open the visualizer in the default browser.")
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_port}"
    print(f"ClimateKG visualizer: {url}")
    if args.open:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
