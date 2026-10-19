"""Run and save query-decomposition plans for a benchmark dataset."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.code_root.resolve()))
    from climatekg.ollama import OllamaClient
    from climatekg.query import decompose_query

    cases = read_json(args.dataset)
    output = args.output.resolve()
    client = OllamaClient()
    records = []
    for index, case in enumerate(cases, 1):
        target = output / "plans" / f"{case['id']}.json"
        if target.exists() and not args.force:
            records.append(read_json(target))
            print(f"[{index}/{len(cases)}] {case['id']}: reused", flush=True)
            continue
        started = time.perf_counter()
        plan, warnings = decompose_query(
            case["question"],
            case["id"],
            client,
            output / "artifacts" / case["id"],
        )
        record = {
            "case_id": case["id"],
            "question": case["question"],
            "operation": plan.operation,
            "subqueries": [item.model_dump() for item in plan.subqueries],
            "warnings": warnings,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(target, record)
        records.append(record)
        print(
            f"[{index}/{len(cases)}] {case['id']}: {plan.operation} ({len(plan.subqueries)})",
            flush=True,
        )

    counts = Counter(record["operation"] for record in records)
    compound = [record["case_id"] for record in records if len(record["subqueries"]) > 1]
    write_json(
        output / "summary.json",
        {
            "case_count": len(records),
            "operation_counts": dict(sorted(counts.items())),
            "compound_case_ids": compound,
            "compound_case_count": len(compound),
            "mean_elapsed_seconds": round(
                sum(record["elapsed_seconds"] for record in records) / len(records), 3
            ),
        },
    )


if __name__ == "__main__":
    main()
