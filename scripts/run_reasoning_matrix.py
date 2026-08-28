from __future__ import annotations

import argparse
import itertools
import json
import shutil
import time
from pathlib import Path
from typing import Any

from climatekg.config import PIPELINE
from climatekg.indexer import index_pdf, load_corpus
from climatekg.parquet_graph import ParquetGraph
from climatekg.utils import write_json


LEVELS = ("low", "no")
MAPPING_STAGES = ("paper_map", "map_consolidation", "paper_map_reference_repair")
CLAIM_STAGES = ("claim_extraction", "claim_reference_repair")
DOWNSTREAM_STAGES = (
    "context_reconciliation",
    "context_reconciliation_reference_repair",
    "paper_consolidation",
)
STABLE_DIRECTORIES = ("source", "parse", "blocks")


def profile_name(mapping: str, claims: str, downstream: str) -> str:
    return f"map-{mapping}_claim-{claims}_down-{downstream}"


def apply_profile(mapping: str, claims: str, downstream: str) -> str:
    name = profile_name(mapping, claims, downstream)
    for stage in MAPPING_STAGES:
        PIPELINE["ollama"]["stages"][stage]["thinking"] = mapping
    for stage in CLAIM_STAGES:
        PIPELINE["ollama"]["stages"][stage]["thinking"] = claims
    for stage in DOWNSTREAM_STAGES:
        PIPELINE["ollama"]["stages"][stage]["thinking"] = downstream
    # These stages are deterministic-reference work or already use no reasoning.
    for stage in ("section_scout", "paper_map_reference_id_repair", "facet_extraction", "facet_reference_repair"):
        PIPELINE["ollama"]["stages"][stage]["thinking"] = "no"
    PIPELINE["ollama"]["reasoning_profile"] = name
    return name


def _copy_directory(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def prepare_paper(
    baseline_root: Path,
    target_root: Path,
    paper_id: str,
    upstream_root: Path | None = None,
    include_claims: bool = False,
) -> None:
    source_paper = baseline_root / "data" / paper_id
    target_paper = target_root / "data" / paper_id
    target_paper.mkdir(parents=True, exist_ok=True)
    for name in STABLE_DIRECTORIES:
        _copy_directory(source_paper / name, target_paper / name)
    manifest = json.loads((source_paper / "manifest.json").read_text(encoding="utf-8"))
    manifest["status"] = "registered"
    manifest.pop("counts", None)
    manifest.pop("failure", None)
    write_json(target_paper / "manifest.json", manifest)
    if upstream_root is None:
        return
    upstream_extraction = upstream_root / "data" / paper_id / "extraction"
    for name in ("map", "facets"):
        _copy_directory(upstream_extraction / name, target_paper / "extraction" / name)
    if include_claims:
        _copy_directory(upstream_extraction / "claims", target_paper / "extraction" / "claims")


def _timing(root: Path, paper_id: str) -> dict[str, float]:
    path = root / "data" / paper_id / "metrics" / "indexing_timing.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    return {item["name"]: item["elapsed_seconds"] for item in report["phases"]}


def _requests(root: Path, paper_id: str) -> list[dict[str, Any]]:
    rows = []
    for path in (root / "data" / paper_id / "extraction").glob("**/*.request.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"path": str(path.resolve()), "think": payload.get("think")})
    return rows


def run_profile(
    *,
    baseline_root: Path,
    output_root: Path,
    input_dir: Path,
    filename: str,
    paper_id: str,
    mapping: str,
    claims: str,
    downstream: str,
    upstream_root: Path | None,
    include_claims: bool,
) -> dict[str, Any]:
    name = apply_profile(mapping, claims, downstream)
    root = output_root / name
    final_path = root / "data" / paper_id / "final" / "final_paper.json"
    if not final_path.exists():
        prepare_paper(baseline_root, root, paper_id, upstream_root, include_claims)
        started = time.perf_counter()
        final = index_pdf(input_dir / filename, root / "data", paper_id)
        elapsed = time.perf_counter() - started
        graph_started = time.perf_counter()
        graph_counts = ParquetGraph(root / "parquet_graph").write_corpus(load_corpus(root / "data"))
        graph_seconds = time.perf_counter() - graph_started
    else:
        from climatekg.models import FinalPaper

        final = FinalPaper.model_validate_json(final_path.read_text(encoding="utf-8"))
        elapsed = sum(_timing(root, paper_id).values())
        graph_seconds = None
        graph_counts = json.loads((root / "parquet_graph" / "manifest.json").read_text(encoding="utf-8"))["tables"]
    row = {
        "profile": name,
        "mapping": mapping,
        "claims": claims,
        "downstream": downstream,
        "wall_seconds": elapsed,
        "phase_seconds": _timing(root, paper_id),
        "counts": {name: len(getattr(final, name)) for name in ("contexts", "facets", "transitions", "claims", "states")},
        "graph_seconds": graph_seconds,
        "graph_counts": graph_counts,
        "upstream_profile": upstream_root.name if upstream_root else None,
        "included_cached_claims": include_claims,
        "requests_present": _requests(root, paper_id),
    }
    write_json(root / "matrix_profile.json", row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, default=Path(r"E:\Atharv\lit_200\files"))
    parser.add_argument("--paper-id", default="P000003")
    parser.add_argument("--filename", default="Effects_of_global_irrigation_on_the_near-surface_c.pdf")
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    # Downstream=no profiles create the controlled upstream artifacts.
    for mapping in LEVELS:
        map_seed_name = profile_name(mapping, "no", "no")
        map_seed = run_profile(
            baseline_root=args.baseline_root,
            output_root=args.output_root,
            input_dir=args.input_dir,
            filename=args.filename,
            paper_id=args.paper_id,
            mapping=mapping,
            claims="no",
            downstream="no",
            upstream_root=None,
            include_claims=False,
        )
        results[map_seed_name] = map_seed
        map_seed_root = args.output_root / map_seed_name
        claim_low_name = profile_name(mapping, "low", "no")
        results[claim_low_name] = run_profile(
            baseline_root=args.baseline_root,
            output_root=args.output_root,
            input_dir=args.input_dir,
            filename=args.filename,
            paper_id=args.paper_id,
            mapping=mapping,
            claims="low",
            downstream="no",
            upstream_root=map_seed_root,
            include_claims=False,
        )

    # Reuse exact map/Facet/Claim artifacts to isolate downstream reasoning.
    for mapping, claims in itertools.product(LEVELS, repeat=2):
        upstream_name = profile_name(mapping, claims, "no")
        downstream_name = profile_name(mapping, claims, "low")
        results[downstream_name] = run_profile(
            baseline_root=args.baseline_root,
            output_root=args.output_root,
            input_dir=args.input_dir,
            filename=args.filename,
            paper_id=args.paper_id,
            mapping=mapping,
            claims=claims,
            downstream="low",
            upstream_root=args.output_root / upstream_name,
            include_claims=True,
        )
        write_json(args.output_root / "matrix_progress.json", list(results.values()))

    ordered = [results[profile_name(*levels)] for levels in itertools.product(LEVELS, repeat=3)]
    write_json(args.output_root / "matrix_summary.json", ordered)
    print(json.dumps({"profiles": len(ordered), "output_root": str(args.output_root.resolve())}))


if __name__ == "__main__":
    main()
