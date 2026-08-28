from __future__ import annotations

import json
import shutil
import threading
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from visualizer.server import ArtifactStore, create_server, without_embeddings


@contextmanager
def workspace_test_dir() -> Iterator[Path]:
    path = Path("visualizer") / ".test_artifacts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def sample_paper() -> dict:
    return {
        "paper": {"id": "P000001", "title": "# Test paper", "year": 2024, "doi": None, "source_file": "test.pdf"},
        "contexts": [{"id": "P000001_C001", "retrieval_embedding": [1.0, 2.0]}],
        "facets": [{"id": "P000001_F001", "content_embedding": [3.0]}],
        "transitions": [],
        "claims": [{"id": "P000001_CL001", "claim_embedding": [4.0]}],
        "states": [],
        "source_blocks": [{"id": "P000001:S00:P0001", "embedding": [5.0]}],
    }


def test_without_embeddings_removes_vectors_recursively() -> None:
    cleaned = without_embeddings({"embedding": [1], "nested": [{"claim_embedding": [2], "id": "kept"}]})
    assert cleaned == {"nested": [{"id": "kept"}]}


def test_graph_nodes_and_edges_have_click_targets() -> None:
    graph_source = Path("visualizer/js/graph.js").read_text(encoding="utf-8")
    app_source = Path("visualizer/js/app.js").read_text(encoding="utf-8")
    assert "ref: claim.id" in graph_source
    assert "this.onSelect(edge.ref)" in graph_source
    assert "this.onSelect(node.ref || node.key, node)" in graph_source
    assert 'graphNode?.type === "state"' in app_source


def test_artifact_store_indexes_papers_and_queries() -> None:
    with workspace_test_dir() as test_dir:
        paper_root = test_dir / "papers"
        query_root = test_dir / "outputs"
        example_root = test_dir / "prompt_examples"
        write_json(paper_root / "P000001" / "final" / "final_paper.json", sample_paper())
        write_json(paper_root / "P000001" / "manifest.json", {"counts": {"contexts": 1, "facets": 1, "claims": 1, "source_blocks": 1}})
        example = sample_paper()
        example["paper"]["title"] = "Surface heterogeneity example"
        write_json(example_root / "atsc-example" / "v2" / "papers" / "P000001" / "final" / "final_paper.json", example)
        write_json(example_root / "atsc-example" / "v2" / "papers" / "P000001" / "manifest.json", {"counts": {"contexts": 1, "facets": 1, "claims": 1, "source_blocks": 1}})
        write_json(query_root / "query-suite-test" / "queries" / "Q001" / "query_report.json", {
            "query_id": "Q001",
            "query_spec": {"user_question": "What changes?", "mode": "forward"},
            "context_candidates": [1],
            "claim_candidates": [1, 2],
            "paths": [],
            "warnings": ["test warning"],
            "answer": "Test answer",
        })

        store = ArtifactStore(paper_root, query_root, [example_root])
        manifest = store.manifest()

        assert manifest["papers"][0]["title"] == "Test paper"
        assert manifest["totals"]["claims"] == 2
        assert manifest["queries"][0]["question"] == "What changes?"
        assert len(manifest["papers"]) == 2
        assert manifest["papers"][1]["artifact_id"].startswith("P000001--atsc-example--v2")
        assert "claim_embedding" not in json.dumps(store.paper("P000001"))


def test_http_api_serves_manifest_and_clean_paper() -> None:
    with workspace_test_dir() as test_dir:
        paper_root = test_dir / "papers"
        query_root = test_dir / "outputs"
        write_json(paper_root / "P000001" / "final" / "final_paper.json", sample_paper())
        write_json(paper_root / "P000001" / "manifest.json", {"counts": {"contexts": 1, "facets": 1, "claims": 1, "source_blocks": 1}})
        store = ArtifactStore(paper_root, query_root)
        server = create_server("127.0.0.1", 0, store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(f"{base}/api/manifest", timeout=5) as response:
                manifest = json.load(response)
            with urllib.request.urlopen(f"{base}/api/papers/P000001", timeout=5) as response:
                paper = json.load(response)
            assert manifest["papers"][0]["id"] == "P000001"
            assert paper["claims"][0]["id"] == "P000001_CL001"
            assert "claim_embedding" not in paper["claims"][0]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
