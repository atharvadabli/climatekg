"""Parse benchmark questions once and save reusable ClimateKG QuerySpecs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--code-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    code_root = args.code_root.resolve()
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(project_root / "climatekg/runtime/cache/tiktoken"))
    sys.path.insert(0, str(code_root))
    sys.path.insert(1, str(project_root))

    from climatekg.config import QUERY_PIPELINE
    from climatekg.geocoding import NominatimGeocoder
    from climatekg.ollama import OllamaClient
    from climatekg.query import parse_query

    # The historical baseline query parser reads this diagnostic attribute,
    # while its matching geocoder revision did not initialize it.
    if not hasattr(NominatimGeocoder, "last_failure_reason"):
        NominatimGeocoder.last_failure_reason = None

    cases = read_json(args.dataset)[:10]
    if args.case:
        requested = set(args.case)
        cases = [case for case in cases if case["id"] in requested]
    client = OllamaClient(QUERY_PIPELINE["ollama"]["base_url"])
    specs_dir = args.output / "specs"
    artifacts_dir = args.output / "artifacts"

    for index, case in enumerate(cases, start=1):
        target = specs_dir / f"{case['id']}.json"
        if target.exists() and not args.force:
            print(f"[{index}/{len(cases)}] {case['id']}: reused", flush=True)
            continue
        print(f"[{index}/{len(cases)}] {case['id']}: parsing", flush=True)
        spec, warnings = parse_query(
            case["question"],
            f"{case['id']}_v2_parse",
            client,
            artifacts_dir / case["id"],
        )
        write_json(target, spec.model_dump(by_alias=True, exclude_none=False))
        write_json(args.output / "warnings" / f"{case['id']}.json", warnings)

    write_json(
        args.output / "manifest.json",
        {
            "dataset": str(args.dataset.resolve()),
            "code_root": str(code_root),
            "case_ids": [case["id"] for case in cases],
            "protocol": "Each v2 question is parsed once; saved QuerySpecs are reused by all ClimateKG variants.",
            "compatibility_note": (
                "The historical geocoder receives a null last_failure_reason class attribute because "
                "the matching query parser reads that attribute although the class did not initialize it."
            ),
        },
    )


if __name__ == "__main__":
    main()
