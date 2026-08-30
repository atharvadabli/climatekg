#!/usr/bin/env python3
"""Assemble one 18-paper ClimateKG data root shared by all three benchmarked systems.

The staged run indexed 17 papers under `indexing_50_medium_map_20260829`. The
heterogeneous-patch paper was indexed separately under `hierarchy_e2e_het_v10`
and reused the identifier `P000001`, which already belongs to the wind-farm
paper in the staged run. This script re-namespaces the heterogeneity artifact to
a free identifier and links the staged artifacts into a single data root, so
`climatekg build-parquet` can produce one graph over exactly the corpus the plain
RAG and GraphRAG baselines already use.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

STAGED_ROOT = Path("climatekg/runtime/outputs/indexing_50_medium_map_20260829/data")
HETEROGENEITY_ARTIFACT = Path("climatekg/runtime/outputs/hierarchy_e2e_het_v10/final/final_paper.json")
DEFAULT_OUTPUT = Path("climatekg/runtime/outputs/three_system_benchmark/climatekg_corpus")


def renamespace(value: object, old: str, new: str) -> object:
    """Rewrite identifier strings that are namespaced by the old paper id."""
    if isinstance(value, str):
        return re.sub(rf"^{old}(?=$|[_:])", new, value)
    if isinstance(value, list):
        return [renamespace(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: renamespace(item, old, new) for key, item in value.items()}
    return value


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-root", type=Path, default=STAGED_ROOT)
    parser.add_argument("--heterogeneity-artifact", type=Path, default=HETEROGENEITY_ARTIFACT)
    parser.add_argument("--heterogeneity-paper-id", default="P000018")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    staged = sorted(args.staged_root.glob("P*/final/final_paper.json"))
    if not staged:
        raise SystemExit(f"no staged papers under {args.staged_root}")
    staged_ids = {path.parent.parent.name for path in staged}
    if args.heterogeneity_paper_id in staged_ids:
        raise SystemExit(f"{args.heterogeneity_paper_id} already used by the staged run")

    manifest: list[dict[str, object]] = []
    for path in staged:
        paper_id = path.parent.parent.name
        destination = args.output / paper_id / "final" / "final_paper.json"
        mode = link_or_copy(path, destination)
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest.append(
            {
                "paper_id": payload["paper"]["id"],
                "source": str(path),
                "materialization": mode,
                "renamespaced_from": None,
                "title": payload["paper"].get("title"),
                "claims": len(payload.get("claims", [])),
                "contexts": len(payload.get("contexts", [])),
                "facets": len(payload.get("facets", [])),
                "source_blocks": len(payload.get("source_blocks", [])),
            }
        )

    payload = json.loads(args.heterogeneity_artifact.read_text(encoding="utf-8"))
    original_id = payload["paper"]["id"]
    payload = renamespace(payload, original_id, args.heterogeneity_paper_id)
    if payload["paper"]["id"] != args.heterogeneity_paper_id:
        raise SystemExit("re-namespacing did not rewrite the paper identifier")
    destination = args.output / args.heterogeneity_paper_id / "final" / "final_paper.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    manifest.append(
        {
            "paper_id": payload["paper"]["id"],
            "source": str(args.heterogeneity_artifact),
            "materialization": "renamespaced_copy",
            "renamespaced_from": original_id,
            "title": payload["paper"].get("title"),
            "claims": len(payload.get("claims", [])),
            "contexts": len(payload.get("contexts", [])),
            "facets": len(payload.get("facets", [])),
            "source_blocks": len(payload.get("source_blocks", [])),
        }
    )

    manifest_path = args.output / "corpus_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "data_root": str(args.output),
                "papers": len(manifest),
                "claims": sum(int(row["claims"]) for row in manifest),
                "contexts": sum(int(row["contexts"]) for row in manifest),
                "facets": sum(int(row["facets"]) for row in manifest),
                "source_blocks": sum(int(row["source_blocks"]) for row in manifest),
                "heterogeneity_paper": args.heterogeneity_paper_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
