from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from climatekg.models import FinalPaper
from climatekg.utils import cosine


def _load_paper(root: Path, paper_id: str) -> FinalPaper:
    path = root / "data" / paper_id / "final" / "final_paper.json"
    return FinalPaper.model_validate_json(path.read_text(encoding="utf-8"))


def _phase_minutes(root: Path, paper_id: str) -> dict[str, float]:
    path = root / "data" / paper_id / "metrics" / "indexing_timing.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    return {item["name"]: item["elapsed_seconds"] / 60 for item in report["phases"]}


def _validate_references(paper: FinalPaper) -> list[str]:
    errors: list[str] = []
    block_ids = {item.id for item in paper.source_blocks}
    context_ids = {item.id for item in paper.contexts}
    transition_ids = {item.id for item in paper.transitions}
    facet_ids = {item.id for item in paper.facets}
    for context in paper.contexts:
        if not set(context.parent_ids) <= context_ids:
            errors.append(f"{context.id}: unknown parent")
        if not set(context.evidence_block_ids) <= block_ids:
            errors.append(f"{context.id}: unknown evidence")
    for facet in paper.facets:
        if facet.context_id not in context_ids or not set(facet.evidence_block_ids) <= block_ids:
            errors.append(f"{facet.id}: invalid Context or evidence")
    for transition in paper.transitions:
        if {transition.from_context_id, transition.to_context_id} - context_ids:
            errors.append(f"{transition.id}: unknown endpoint")
        if not set(transition.evidence_block_ids) <= block_ids:
            errors.append(f"{transition.id}: unknown evidence")
    for claim in paper.claims:
        if claim.scope_id not in context_ids | transition_ids:
            errors.append(f"{claim.id}: unknown scope")
        if not set(claim.conditioning_facet_ids) <= facet_ids:
            errors.append(f"{claim.id}: unknown conditioning Facet")
        if not set(claim.evidence_block_ids) <= block_ids:
            errors.append(f"{claim.id}: unknown evidence")
    return errors


def _alignment(left: list[Any], right: list[Any], vector_field: str) -> dict[str, Any]:
    rows = []
    for item in left:
        vector = getattr(item, vector_field) or []
        matches = [(cosine(vector, getattr(candidate, vector_field) or []), candidate) for candidate in right]
        score, match = max(matches, key=lambda row: row[0]) if matches else (0.0, None)
        evidence_overlap = None
        if match is not None and hasattr(item, "evidence_block_ids"):
            a, b = set(item.evidence_block_ids), set(match.evidence_block_ids)
            evidence_overlap = len(a & b) / len(a | b) if a | b else 1.0
        rows.append({"baseline_id": item.id, "new_id": match.id if match else None, "cosine": score, "evidence_jaccard": evidence_overlap})
    scores = [row["cosine"] for row in rows]
    overlaps = [row["evidence_jaccard"] for row in rows if row["evidence_jaccard"] is not None]
    return {
        "items": len(rows),
        "median_max_cosine": statistics.median(scores) if scores else None,
        "fraction_at_least_0_80": sum(score >= 0.80 for score in scores) / len(scores) if scores else None,
        "fraction_at_least_0_90": sum(score >= 0.90 for score in scores) / len(scores) if scores else None,
        "mean_evidence_jaccard": statistics.mean(overlaps) if overlaps else None,
        "lowest_matches": sorted(rows, key=lambda row: row["cosine"])[:5],
    }


def _llm_request_summary(root: Path, paper_ids: list[str]) -> dict[str, Any]:
    requests = [path for paper_id in paper_ids for path in (root / "data" / paper_id / "extraction").glob("**/*.request.json")]
    think_values = []
    for path in requests:
        payload = json.loads(path.read_text(encoding="utf-8"))
        think_values.append(payload.get("think"))
    return {
        "requests": len(requests),
        "all_think_false": bool(requests) and all(value is False for value in think_values),
        "non_false_values": [value for value in think_values if value is not False],
    }


def compare(baseline_root: Path, new_root: Path, paper_ids: list[str]) -> dict[str, Any]:
    rows = []
    for paper_id in paper_ids:
        baseline, new = _load_paper(baseline_root, paper_id), _load_paper(new_root, paper_id)
        baseline_phases, new_phases = _phase_minutes(baseline_root, paper_id), _phase_minutes(new_root, paper_id)
        baseline_total, new_total = sum(baseline_phases.values()), sum(new_phases.values())
        rows.append({
            "paper_id": paper_id,
            "baseline_minutes": baseline_total,
            "new_minutes": new_total,
            "speedup": baseline_total / new_total,
            "reduction_fraction": 1 - new_total / baseline_total,
            "counts": {
                name: {"baseline": len(getattr(baseline, name)), "new": len(getattr(new, name))}
                for name in ("source_blocks", "contexts", "facets", "transitions", "claims", "states")
            },
            "reference_errors": _validate_references(new),
            "context_alignment_baseline_to_new": _alignment(baseline.contexts, new.contexts, "retrieval_embedding"),
            "context_alignment_new_to_baseline": _alignment(new.contexts, baseline.contexts, "retrieval_embedding"),
            "claim_alignment_baseline_to_new": _alignment(baseline.claims, new.claims, "claim_embedding"),
            "claim_alignment_new_to_baseline": _alignment(new.claims, baseline.claims, "claim_embedding"),
            "phase_minutes": {
                name: {"baseline": baseline_phases.get(name), "new": new_phases.get(name)}
                for name in sorted(set(baseline_phases) | set(new_phases))
            },
        })
    return {
        "baseline_root": str(baseline_root.resolve()),
        "new_root": str(new_root.resolve()),
        "llm_requests": _llm_request_summary(new_root, paper_ids),
        "papers": rows,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# No-Reasoning Indexing Ablation",
        "",
        "Generated by `scripts/compare_indexing_ablation.py`.",
        "",
        f"All new LLM requests used `think: false`: **{report['llm_requests']['all_think_false']}** "
        f"({report['llm_requests']['requests']} requests).",
        "",
        "| Paper | Baseline min | No-reasoning min | Reduction | Speedup | Reference errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["papers"]:
        lines.append(f"| `{row['paper_id']}` | {row['baseline_minutes']:.2f} | {row['new_minutes']:.2f} | {row['reduction_fraction']:.1%} | {row['speedup']:.2f}x | {len(row['reference_errors'])} |")
    lines.extend(["", "## Object Counts", "", "| Paper | Object | Baseline | No reasoning |", "|---|---|---:|---:|"])
    for row in report["papers"]:
        for name, counts in row["counts"].items():
            lines.append(f"| `{row['paper_id']}` | {name} | {counts['baseline']} | {counts['new']} |")
    lines.extend(["", "## Semantic Alignment", "", "These are diagnostic embedding matches, not exact-string checks or scientific truth scores.", "", "| Paper | Direction | Context median / >=.80 | Claim median / >=.80 | Claim evidence Jaccard |", "|---|---|---:|---:|---:|"])
    for row in report["papers"]:
        for direction in ("baseline_to_new", "new_to_baseline"):
            context = row[f"context_alignment_{direction}"]
            claim = row[f"claim_alignment_{direction}"]
            lines.append(f"| `{row['paper_id']}` | {direction.replace('_', ' ')} | {context['median_max_cosine']:.3f} / {context['fraction_at_least_0_80']:.1%} | {claim['median_max_cosine']:.3f} / {claim['fraction_at_least_0_80']:.1%} | {claim['mean_evidence_jaccard']:.3f} |")
    lines.extend(["", "## Interpretation", "", "Reference integrity is a hard check. Semantic alignment is only a review aid: changed granularity can legitimately change counts and nearest-neighbor scores. Low-alignment objects and context trees must be reviewed against SourceBlocks before adopting the faster profile."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--paper-id", action="append", required=True, dest="paper_ids")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.baseline_root, args.new_root, args.paper_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_markdown(report), encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
