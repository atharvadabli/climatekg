from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from climatekg.models import FinalPaper
from climatekg.utils import cosine, write_json


FIXED_INITIAL_PHASES = (
    "paper_registration",
    "pdf_parse_nemotron",
    "parse_cleaning",
    "sourceblock_generation",
    "sourceblock_embeddings",
    "permanent_context_transition_ids",
)
FINAL_PHASES = ("state_canonicalization", "final_object_embeddings", "final_artifact_assembly")


def _paper(root: Path, paper_id: str) -> FinalPaper:
    path = root / "data" / paper_id / "final" / "final_paper.json"
    return FinalPaper.model_validate_json(path.read_text(encoding="utf-8"))


def _phases(root: Path, paper_id: str) -> dict[str, float]:
    path = root / "data" / paper_id / "metrics" / "indexing_timing.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    return {item["name"]: item["elapsed_seconds"] for item in report["phases"]}


def _reference_errors(paper: FinalPaper) -> list[str]:
    blocks = {item.id for item in paper.source_blocks}
    contexts = {item.id for item in paper.contexts}
    transitions = {item.id for item in paper.transitions}
    facets = {item.id for item in paper.facets}
    errors = []
    for context in paper.contexts:
        if not set(context.parent_ids) <= contexts or not set(context.evidence_block_ids) <= blocks:
            errors.append(context.id)
    for facet in paper.facets:
        if facet.context_id not in contexts or not set(facet.evidence_block_ids) <= blocks:
            errors.append(facet.id)
    for transition in paper.transitions:
        if {transition.from_context_id, transition.to_context_id} - contexts or not set(transition.evidence_block_ids) <= blocks:
            errors.append(transition.id)
    for claim in paper.claims:
        if claim.scope_id not in contexts | transitions or not set(claim.conditioning_facet_ids) <= facets or not set(claim.evidence_block_ids) <= blocks:
            errors.append(claim.id)
    return errors


def _alignment(left: list[Any], right: list[Any], vector_field: str) -> dict[str, float | None]:
    scores = []
    for item in left:
        vector = getattr(item, vector_field) or []
        scores.append(max((cosine(vector, getattr(candidate, vector_field) or []) for candidate in right), default=0.0))
    return {
        "median": statistics.median(scores) if scores else None,
        "fraction_at_least_0_80": sum(score >= 0.80 for score in scores) / len(scores) if scores else None,
        "fraction_at_least_0_90": sum(score >= 0.90 for score in scores) / len(scores) if scores else None,
    }


def _duplicate_transition_pairs(paper: FinalPaper) -> int:
    pairs = [(item.from_context_id, item.to_context_id) for item in paper.transitions]
    return len(pairs) - len(set(pairs))


def _profile_parts(name: str) -> tuple[str, str, str]:
    parts = name.replace("map-", "").replace("claim-", "").replace("down-", "").split("_")
    return parts[0], parts[1], parts[2]


def _projected_seconds(matrix_root: Path, baseline_root: Path, profile: str, paper_id: str) -> tuple[float, dict[str, float | str]]:
    mapping, claims, downstream = _profile_parts(profile)
    map_source = matrix_root / f"map-{mapping}_claim-no_down-no"
    claim_source = matrix_root / f"map-{mapping}_claim-{claims}_down-no"
    final_source = matrix_root / profile
    baseline = _phases(baseline_root, paper_id)
    map_phases = _phases(map_source, paper_id)
    claim_phases = _phases(claim_source, paper_id)
    final_phases = _phases(final_source, paper_id)
    components: dict[str, float | str] = {
        "fixed_initial_seconds": sum(baseline.get(name, 0.0) for name in FIXED_INITIAL_PHASES),
        "mapping_seconds": map_phases["paper_mapping"],
        "facet_seconds": map_phases["facet_extraction"],
        "claim_seconds": claim_phases["claim_extraction"],
        "reconciliation_seconds": final_phases["context_reconciliation"],
        "consolidation_seconds": final_phases["paper_consolidation"],
        "final_seconds": sum(final_phases.get(name, 0.0) for name in FINAL_PHASES),
        "map_source": map_source.name,
        "claim_source": claim_source.name,
        "downstream_source": final_source.name,
    }
    total = sum(value for value in components.values() if isinstance(value, float))
    return total, components


def build_report(matrix_root: Path, baseline_root: Path, paper_id: str) -> dict[str, Any]:
    baseline = _paper(baseline_root, paper_id)
    rows = []
    for profile_root in sorted(path for path in matrix_root.iterdir() if path.is_dir() and (path / "data" / paper_id / "final" / "final_paper.json").exists()):
        paper = _paper(profile_root, paper_id)
        projected, components = _projected_seconds(matrix_root, baseline_root, profile_root.name, paper_id)
        context_forward = _alignment(baseline.contexts, paper.contexts, "retrieval_embedding")
        context_reverse = _alignment(paper.contexts, baseline.contexts, "retrieval_embedding")
        claim_forward = _alignment(baseline.claims, paper.claims, "claim_embedding")
        claim_reverse = _alignment(paper.claims, baseline.claims, "claim_embedding")
        row = {
            "profile": profile_root.name,
            "projected_fresh_seconds": projected,
            "components": components,
            "counts": {name: len(getattr(paper, name)) for name in ("contexts", "facets", "transitions", "claims", "states")},
            "reference_errors": _reference_errors(paper),
            "duplicate_transition_endpoint_pairs": _duplicate_transition_pairs(paper),
            "context_alignment_baseline_to_profile": context_forward,
            "context_alignment_profile_to_baseline": context_reverse,
            "claim_alignment_baseline_to_profile": claim_forward,
            "claim_alignment_profile_to_baseline": claim_reverse,
        }
        row["quality_gate"] = (
            not row["reference_errors"]
            and row["duplicate_transition_endpoint_pairs"] == 0
            and context_forward["fraction_at_least_0_80"] == 1.0
            and context_reverse["fraction_at_least_0_80"] == 1.0
            and claim_forward["fraction_at_least_0_80"] >= 0.90
            and claim_reverse["fraction_at_least_0_80"] >= 0.90
        )
        rows.append(row)
        write_json(profile_root / "benchmark.json", row)
        (profile_root / "BENCHMARK.md").write_text(_profile_markdown(row, baseline_root, paper_id), encoding="utf-8")
    report = {"paper_id": paper_id, "baseline_root": str(baseline_root.resolve()), "profiles": rows}
    write_json(matrix_root / "reasoning_matrix_benchmark.json", report)
    (matrix_root / "BENCHMARK.md").write_text(_matrix_markdown(report), encoding="utf-8")
    return report


def _profile_markdown(row: dict[str, Any], baseline_root: Path, paper_id: str) -> str:
    mapping, claims, downstream = _profile_parts(row["profile"])
    components = row["components"]
    return f"""# Reasoning Profile Benchmark

Profile: `{row['profile']}`

## Effective Settings

- Mapping: `{mapping}`
- Claim extraction: `{claims}`
- Context reconciliation and paper consolidation: `{downstream}`
- Facet extraction and section scouting: `no`

## Runtime

Estimated fresh end-to-end runtime: **{row['projected_fresh_seconds'] / 60:.2f} minutes**.

The matrix reused exact upstream artifacts to isolate factors. This estimate combines the measured
fresh parser cost from `{baseline_root}` with the following measured component sources:

| Component | Minutes | Source profile |
|---|---:|---|
| Fixed parsing and SourceBlocks | {components['fixed_initial_seconds'] / 60:.2f} | baseline `{paper_id}` |
| Mapping | {components['mapping_seconds'] / 60:.2f} | `{components['map_source']}` |
| Facets | {components['facet_seconds'] / 60:.2f} | `{components['map_source']}` |
| Claims | {components['claim_seconds'] / 60:.2f} | `{components['claim_source']}` |
| Reconciliation | {components['reconciliation_seconds'] / 60:.2f} | `{components['downstream_source']}` |
| Consolidation | {components['consolidation_seconds'] / 60:.2f} | `{components['downstream_source']}` |
| State/final embeddings/assembly | {components['final_seconds'] / 60:.2f} | `{components['downstream_source']}` |

## Output and Integrity

| Contexts | Facets | Transitions | Claims | States |
|---:|---:|---:|---:|---:|
| {row['counts']['contexts']} | {row['counts']['facets']} | {row['counts']['transitions']} | {row['counts']['claims']} | {row['counts']['states']} |

- Reference errors: **{len(row['reference_errors'])}**
- Duplicate Transition endpoint pairs: **{row['duplicate_transition_endpoint_pairs']}**
- Deterministic/semantic screening gate: **{'PASS' if row['quality_gate'] else 'FAIL'}**
- Context median alignment, baseline to profile: `{row['context_alignment_baseline_to_profile']['median']:.3f}`
- Claim median alignment, baseline to profile: `{row['claim_alignment_baseline_to_profile']['median']:.3f}`

Embedding alignment is a review diagnostic, not an exact-string requirement or scientific truth score.
"""


def _matrix_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Reasoning Matrix Benchmark",
        "",
        f"Screening paper: `{report['paper_id']}`",
        "",
        "| Profile | Estimated fresh min | C/F/T/CL | Duplicate endpoints | Context median | Claim median | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(report["profiles"], key=lambda item: item["projected_fresh_seconds"]):
        counts = row["counts"]
        lines.append(
            f"| `{row['profile']}` | {row['projected_fresh_seconds'] / 60:.2f} | "
            f"{counts['contexts']}/{counts['facets']}/{counts['transitions']}/{counts['claims']} | "
            f"{row['duplicate_transition_endpoint_pairs']} | "
            f"{row['context_alignment_baseline_to_profile']['median']:.3f} | "
            f"{row['claim_alignment_baseline_to_profile']['median']:.3f} | "
            f"{'PASS' if row['quality_gate'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "Each profile directory contains its own `BENCHMARK.md` and `benchmark.json`.",
        "Projected times reconstruct a fresh run from controlled component measurements; cache-assisted wall times are not presented as fresh indexing times.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--paper-id", default="P000003")
    args = parser.parse_args()
    report = build_report(args.matrix_root, args.baseline_root, args.paper_id)
    print(json.dumps({"profiles": len(report["profiles"]), "report": str((args.matrix_root / 'BENCHMARK.md').resolve())}))


if __name__ == "__main__":
    main()
