from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import faiss
import numpy as np

from .models import FinalPaper
from .utils import write_json

INDEX_VERSION = "1.0"
VECTOR_FIELDS = {
    "contexts": "retrieval_embedding",
    "claims": "claim_embedding",
    "states": "concept_embedding",
    "transitions": "transition_embedding",
}


class FaissIndexes:
    """Persisted HNSW indexes used only for candidate generation."""

    def __init__(self, root: Path, manifest: dict, indexes: dict[str, faiss.Index]) -> None:
        self.root = Path(root)
        self.manifest = manifest
        self.indexes = indexes

    @classmethod
    def build(
        cls,
        papers: Iterable[FinalPaper],
        root: Path,
        dimension: int,
        connectivity: int = 32,
        ef_construction: int = 200,
        ef_search: int = 128,
    ) -> "FaissIndexes":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        papers = list(papers)
        collections = _collections(papers)
        manifest = {
            "format": "climatekg-faiss-hnsw",
            "format_version": INDEX_VERSION,
            "dimension": dimension,
            "metric": "cosine",
            "connectivity": connectivity,
            "ef_construction": ef_construction,
            "ef_search": ef_search,
            "collections": {},
        }
        indexes: dict[str, faiss.Index] = {}
        for name, items in collections.items():
            identifiers = [identifier for identifier, _ in items]
            matrix = _matrix([vector for _, vector in items], dimension)
            index = faiss.IndexHNSWFlat(dimension, connectivity, faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = ef_construction
            index.hnsw.efSearch = ef_search
            if len(matrix):
                index.add(matrix)
            faiss.write_index(index, str(root / f"{name}.faiss"))
            manifest["collections"][name] = {"ids": identifiers, "count": len(identifiers)}
            indexes[name] = index
        write_json(root / "manifest.json", manifest)
        return cls(root, manifest, indexes)

    @classmethod
    def load(cls, root: Path) -> "FaissIndexes":
        root = Path(root)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"FAISS index manifest not found: {manifest_path}; rebuild the Parquet graph")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != "climatekg-faiss-hnsw" or manifest.get("format_version") != INDEX_VERSION:
            raise ValueError(f"Unsupported FAISS index format: {manifest}")
        indexes = {}
        for name in VECTOR_FIELDS:
            path = root / f"{name}.faiss"
            if not path.exists():
                raise FileNotFoundError(f"Required FAISS index not found: {path}")
            index = faiss.read_index(str(path))
            index.hnsw.efSearch = manifest["ef_search"]
            expected = manifest["collections"][name]["count"]
            if index.ntotal != expected:
                raise ValueError(f"FAISS index count mismatch for {name}: {index.ntotal} != {expected}")
            indexes[name] = index
        return cls(root, manifest, indexes)

    def search(self, collection: str, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if collection not in VECTOR_FIELDS:
            raise KeyError(f"Unknown ANN collection: {collection}")
        identifiers = self.manifest["collections"][collection]["ids"]
        if not vector or not identifiers or top_k <= 0:
            return []
        query = _matrix([vector], self.manifest["dimension"])
        scores, positions = self.indexes[collection].search(query, min(top_k, len(identifiers)))
        return [
            (identifiers[position], max(0.0, float(score)))
            for position, score in zip(positions[0], scores[0])
            if position >= 0
        ]


def _matrix(vectors: list[list[float]], dimension: int) -> np.ndarray:
    if not vectors:
        return np.empty((0, dimension), dtype=np.float32)
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != dimension:
        raise ValueError(f"Embedding dimension mismatch: expected {dimension}, got {matrix.shape}")
    faiss.normalize_L2(matrix)
    return matrix


def _collections(papers: list[FinalPaper]) -> dict[str, list[tuple[str, list[float]]]]:
    result: dict[str, list[tuple[str, list[float]]]] = {}
    for name, field in VECTOR_FIELDS.items():
        seen: dict[str, list[float]] = {}
        for paper in papers:
            for item in getattr(paper, name):
                vector = getattr(item, field)
                if vector is None:
                    raise ValueError(f"Missing {field} for {item.id}")
                previous = seen.get(item.id)
                if previous is not None and previous != vector:
                    raise ValueError(f"Conflicting embeddings for shared ID {item.id}")
                seen[item.id] = vector
        result[name] = sorted(seen.items())
    return result
