from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climatekg.models import FinalPaper
from climatekg.utils import cosine, write_json


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare ClimateKG full-scan and FAISS HNSW retrieval scaling.")
    parser.add_argument("--source-final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[26, 260, 2600, 26000])
    return parser.parse_args()


def _full_scan(vectors: list[list[float]], size: int, top_k: int) -> float:
    query = vectors[0]
    started = time.perf_counter()
    sorted(
        ((max(0.0, cosine(query, vectors[index % len(vectors)])), index) for index in range(size)),
        key=lambda item: (-item[0], item[1]),
    )[:top_k]
    return time.perf_counter() - started


def _synthetic_matrix(base: np.ndarray, size: int) -> np.ndarray:
    rng = np.random.default_rng(20260828 + size)
    matrix = np.tile(base, (size // len(base) + 1, 1))[:size]
    matrix += rng.normal(0.0, 0.01, matrix.shape).astype(np.float32)
    faiss.normalize_L2(matrix)
    return matrix


def _hnsw(matrix: np.ndarray, top_k: int) -> dict[str, float]:
    dimension = matrix.shape[1]
    index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = 200
    index.hnsw.efSearch = 128
    started = time.perf_counter()
    index.add(matrix)
    build_seconds = time.perf_counter() - started

    query = matrix[0:1]
    exact_scores = matrix @ query[0]
    exact_ids = set(np.argpartition(exact_scores, -top_k)[-top_k:].tolist())
    samples = []
    found: set[int] = set()
    for _ in range(20):
        started = time.perf_counter()
        _, positions = index.search(query, top_k)
        samples.append(time.perf_counter() - started)
        found = set(positions[0].tolist())
    return {
        "build_seconds": build_seconds,
        "median_query_seconds": statistics.median(samples),
        "recall_at_k": len(exact_ids & found) / top_k,
        "index_bytes_estimate": int(index.ntotal * (dimension * 4 + 32 * 2 * 4)),
    }


def main() -> None:
    args = _arguments()
    paper = FinalPaper.model_validate_json(args.source_final.read_text(encoding="utf-8"))
    vectors = [context.retrieval_embedding for context in paper.contexts if context.retrieval_embedding]
    base = np.asarray(vectors, dtype=np.float32)
    faiss.normalize_L2(base)
    rows = []
    for size in args.sizes:
        top_k = min(100, size)
        scan_seconds = _full_scan(vectors, size, top_k)
        matrix = _synthetic_matrix(base, size)
        ann = _hnsw(matrix, top_k)
        row = {
            "vectors": size,
            "dimension": base.shape[1],
            "equivalent_papers_at_26_contexts_each": size / 26,
            "python_full_scan_seconds": scan_seconds,
            **ann,
            "query_speedup": scan_seconds / ann["median_query_seconds"],
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    write_json(args.output, {"benchmark": "context_candidate_generation", "rows": rows})


if __name__ == "__main__":
    main()
