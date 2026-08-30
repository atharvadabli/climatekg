#!/usr/bin/env python3
"""Measure staged-extraction recall against the hand-annotated ground truth.

For each annotated paper this compares the study settings and own-result
relationships a reader can support from the parsed text with what the qwen3.6:27b
staged pipeline actually emitted, and reports recall plus the categories of
missed evidence. The annotation files under `config/extraction_ground_truth/`
carry the match decisions; this script only aggregates them and verifies that
every claimed match points at a claim the pipeline really produced.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

DEFAULT_GROUND_TRUTH = Path("config/extraction_ground_truth")
DEFAULT_CORPUS = Path("climatekg/runtime/outputs/three_system_benchmark/climatekg_corpus")


def load_extraction(corpus_root: Path, paper_id: str) -> dict[str, Any]:
    path = corpus_root / paper_id / "final" / "final_paper.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "contexts": {row["id"] for row in payload["contexts"]},
        "claims": {row["id"]: row for row in payload["claims"]},
        "transitions": {row["id"] for row in payload["transitions"]},
    }


def audit_paper(annotation: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    claims = annotation["claims"]
    matched, unmatched, invalid = [], [], []
    redundant: set[str] = set()
    for claim in claims:
        for duplicate in claim.get("duplicate_claim_ids", []):
            if duplicate in extraction["claims"]:
                redundant.add(duplicate)
            else:
                invalid.append({"key": claim["key"], "duplicate_claim_id": duplicate})
        target = claim.get("matched_claim_id")
        if target is None:
            unmatched.append(claim["key"])
        elif target in extraction["claims"]:
            matched.append(claim["key"])
        else:
            invalid.append({"key": claim["key"], "matched_claim_id": target})
    roles = collections.Counter(claim["role"] for claim in claims)
    # A record is unsupported only when it maps to no reference claim at all;
    # extra records that restate a matched reference claim are counted as redundant.
    unsupported = len(extraction["claims"]) - len(matched) - len(redundant)
    by_key = {claim["key"]: claim for claim in claims}
    main = [claim for claim in claims if claim.get("tier") == "main"]
    main_matched = [key for key in matched if by_key[key].get("tier") == "main"]
    return {
        "paper_id": annotation["paper_id"],
        "title": annotation["title"],
        "reference_settings": len(annotation["settings"]),
        "extracted_settings": len(extraction["contexts"]),
        "setting_recall": round(len(extraction["contexts"]) / len(annotation["settings"]), 3)
        if annotation["settings"]
        else None,
        "reference_claims": len(claims),
        "extracted_claims": len(extraction["claims"]),
        "matched_claims": len(matched),
        "claim_recall": round(len(matched) / len(claims), 3) if claims else None,
        "main_claims": len(main),
        "main_matched": len(main_matched),
        "main_claim_recall": round(len(main_matched) / len(main), 3) if main else None,
        "redundant_claims": len(redundant),
        "unsupported_claims": unsupported,
        "reference_roles": dict(roles),
        "missed_main_claim_keys": [
            claim["key"] for claim in main if claim.get("matched_claim_id") is None
        ],
        "missed_claim_keys": unmatched,
        "invalid_matches": invalid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = []
    for path in sorted(args.ground_truth.glob("P*.json")):
        annotation = json.loads(path.read_text(encoding="utf-8"))
        extraction = load_extraction(args.corpus, annotation["paper_id"])
        rows.append(audit_paper(annotation, extraction))

    if not rows:
        raise SystemExit(f"no annotation files under {args.ground_truth}")

    reference_settings = sum(row["reference_settings"] for row in rows)
    extracted_settings = sum(row["extracted_settings"] for row in rows)
    reference_claims = sum(row["reference_claims"] for row in rows)
    matched_claims = sum(row["matched_claims"] for row in rows)
    extracted_claims = sum(row["extracted_claims"] for row in rows)
    summary = {
        "papers": len(rows),
        "reference_settings": reference_settings,
        "extracted_settings": extracted_settings,
        "setting_ratio": round(extracted_settings / reference_settings, 3) if reference_settings else None,
        "reference_claims": reference_claims,
        "extracted_claims": extracted_claims,
        "matched_claims": matched_claims,
        "claim_recall": round(matched_claims / reference_claims, 3) if reference_claims else None,
        "main_claims": sum(row["main_claims"] for row in rows),
        "main_matched": sum(row["main_matched"] for row in rows),
        "main_claim_recall": round(
            sum(row["main_matched"] for row in rows) / sum(row["main_claims"] for row in rows), 3
        )
        if sum(row["main_claims"] for row in rows)
        else None,
        "redundant_claims": sum(row["redundant_claims"] for row in rows),
        "unsupported_claims": sum(row["unsupported_claims"] for row in rows),
        "claim_precision": round(
            (matched_claims + sum(row["redundant_claims"] for row in rows)) / extracted_claims, 3
        )
        if extracted_claims
        else None,
        "invalid_matches": [item for row in rows for item in row["invalid_matches"]],
    }

    print(
        f"{'paper':9} {'ref_set':>8} {'ext_set':>8} {'main':>5} {'m_hit':>6} {'m_rec':>7} "
        f"{'all':>5} {'a_rec':>7} {'dup':>4} {'unsup':>6}  title"
    )
    for row in rows:
        print(
            f"{row['paper_id']:9} {row['reference_settings']:>8} {row['extracted_settings']:>8} "
            f"{row['main_claims']:>5} {row['main_matched']:>6} {str(row['main_claim_recall']):>7} "
            f"{row['reference_claims']:>5} {str(row['claim_recall']):>7} "
            f"{row['redundant_claims']:>4} {row['unsupported_claims']:>6}  {row['title'][:36]}"
        )
    print()
    print(json.dumps(summary, indent=2))
    if summary["invalid_matches"]:
        raise SystemExit("annotation references claim ids that the pipeline did not produce")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"summary": summary, "papers": rows}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nwritten: {args.output}")


if __name__ == "__main__":
    main()
