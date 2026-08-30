#!/usr/bin/env python3
"""Build and query plain RAG and entity-adapted GraphRAG on one corpus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from climatekg.constants import OLLAMA_CONTEXT_TOKENS

from .corpus import discover_papers, export_plain_rag
from .graphrag_adapter import build_index, query_index


def run_command(command: list[str], output: Path) -> float:
    started = time.perf_counter()
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "CLIMATEKG_OLLAMA_CONTEXT_TOKENS": str(OLLAMA_CONTEXT_TOKENS),
        },
        capture_output=True,
        check=False,
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    output.write_text(stdout + ("\nSTDERR\n" + stderr if stderr else ""), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {output}")
    return time.perf_counter() - started


def valid_plain_index(index_dir: Path) -> bool:
    chunks = index_dir / "chunks.jsonl"
    meta = index_dir / "meta.json"
    if not chunks.exists() or not meta.exists() or chunks.stat().st_size == 0:
        return False
    try:
        with chunks.open("r", encoding="utf-8") as handle:
            return all(isinstance(json.loads(line), dict) for line in handle if line.strip())
    except (OSError, json.JSONDecodeError):
        return False


def json_default(value: object) -> object:
    if hasattr(value, "tolist"):
        return value.tolist()  # type: ignore[union-attr]
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-root", type=Path, required=True)
    parser.add_argument("--heterogeneity-root", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="qwen3-embedding:4b")
    parser.add_argument("--chat-model", default="qwen3.6:27b")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    papers = discover_papers([args.staged_root, args.heterogeneity_root])
    manifest = export_plain_rag(papers, args.output / "corpus")
    queries = json.loads(args.queries.read_text(encoding="utf-8"))["queries"]

    plain_dir = args.output / "plain_rag"
    plain_dir.mkdir(exist_ok=True)
    plain_script = Path("baselines/plain_rag/plain_rag.py").resolve()
    plain_python = sys.executable
    if valid_plain_index(plain_dir / "index"):
        build_seconds = 0.0
    else:
        build_seconds = run_command(
            [
                plain_python,
                str(plain_script),
                "--source-csv",
                str(manifest),
                "--index-dir",
                str(plain_dir / "index"),
                "--ollama-url",
                args.ollama_url,
                "--embed-model",
                args.embed_model,
                "build",
            ],
            plain_dir / "build.log",
        )
    timings_path = plain_dir / "timings.json"
    plain_timings = (
        json.loads(timings_path.read_text(encoding="utf-8"))
        if timings_path.exists()
        else {"build_seconds": round(build_seconds, 3), "queries": {}}
    )
    for query in queries:
        query_output = plain_dir / f"{query['id']}.txt"
        if query_output.exists() and query_output.stat().st_size > 0:
            continue
        elapsed = run_command(
            [
                plain_python,
                str(plain_script),
                "--index-dir",
                str(plain_dir / "index"),
                "--ollama-url",
                args.ollama_url,
                "--embed-model",
                args.embed_model,
                "--chat-model",
                args.chat_model,
                "query",
                "--top-k",
                "8",
                query["question"],
            ],
            query_output,
        )
        plain_timings["queries"][query["id"]] = round(elapsed, 3)
    timings_path.write_text(json.dumps(plain_timings, indent=2), encoding="utf-8")

    graph_dir = args.output / "graphrag"
    vendor_root = Path("baselines/graphrag/packages/graphrag").resolve()
    graph_meta_path = graph_dir / "meta.json"
    if graph_meta_path.exists() and all(
        (graph_dir / name).exists()
        for name in ("entities.parquet", "relationships.parquet", "text_units.parquet", "communities.parquet")
    ):
        graph_meta = json.loads(graph_meta_path.read_text(encoding="utf-8"))
    else:
        graph_meta = build_index(papers, graph_dir, vendor_root, args.ollama_url, args.embed_model)
    for query in queries:
        query_output = graph_dir / f"{query['id']}.json"
        if query_output.exists() and query_output.stat().st_size > 0:
            continue
        result = query_index(
            graph_dir,
            query["question"],
            args.ollama_url,
            args.embed_model,
            args.chat_model,
        )
        query_output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8"
        )
    print(json.dumps({"paper_count": len(papers), "plain_rag": plain_timings, "graphrag": graph_meta}, indent=2))


if __name__ == "__main__":
    main()
