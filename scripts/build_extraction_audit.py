from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.run_three_system_benchmark import DEFAULT_SOURCE_ROOT, load_shared_corpus


DEFAULT_OUTPUT = REPOSITORY_ROOT / "climatekg" / "runtime" / "outputs" / "extraction_audit_20260830"
SELECTED_PAPERS = (
    "R2_P000001",
    "R1_P000002",
    "R1_P000003",
    "R1_P000004",
    "R1_P000005",
    "R1_P000006",
    "R1_P000014",
    "R1_P000015",
    "R1_P000019",
    "R1_P000020",
)


def unresolved(values: list[str], known: set[str]) -> list[str]:
    return sorted(value for value in values if value not in known)


def audit_paper(paper) -> dict:
    block_ids = {item.id for item in paper.source_blocks}
    facet_ids = {item.id for item in paper.facets}
    context_ids = {item.id for item in paper.contexts}
    transition_ids = {item.id for item in paper.transitions}
    object_ids = context_ids | transition_ids
    errors = []

    for facet in paper.facets:
        missing = unresolved(facet.evidence_block_ids, block_ids)
        if missing:
            errors.append({"object_id": facet.id, "field": "evidence_block_ids", "unresolved": missing})
    for context in paper.contexts:
        missing_blocks = unresolved(context.evidence_block_ids, block_ids)
        missing_parents = unresolved(context.parent_ids, context_ids)
        if missing_blocks:
            errors.append({"object_id": context.id, "field": "evidence_block_ids", "unresolved": missing_blocks})
        if missing_parents:
            errors.append({"object_id": context.id, "field": "parent_ids", "unresolved": missing_parents})
    for facet in paper.facets:
        if facet.context_id not in context_ids:
            errors.append({"object_id": facet.id, "field": "context_id", "unresolved": [facet.context_id]})
    for transition in paper.transitions:
        missing_blocks = unresolved(transition.evidence_block_ids, block_ids)
        missing_contexts = unresolved([transition.from_context_id, transition.to_context_id], context_ids)
        if missing_blocks:
            errors.append({"object_id": transition.id, "field": "evidence_block_ids", "unresolved": missing_blocks})
        if missing_contexts:
            errors.append({"object_id": transition.id, "field": "context_ids", "unresolved": missing_contexts})
    for claim in paper.claims:
        missing_blocks = unresolved(claim.evidence_block_ids, block_ids)
        missing_facets = unresolved(claim.conditioning_facet_ids, facet_ids)
        if missing_blocks:
            errors.append({"object_id": claim.id, "field": "evidence_block_ids", "unresolved": missing_blocks})
        if missing_facets:
            errors.append({"object_id": claim.id, "field": "conditioning_facet_ids", "unresolved": missing_facets})
        if claim.scope_id not in object_ids:
            errors.append({"object_id": claim.id, "field": "scope_id", "unresolved": [claim.scope_id]})

    return {
        "paper_id": paper.paper.id,
        "title": paper.paper.title,
        "counts": {
            "source_blocks": len(paper.source_blocks),
            "contexts": len(paper.contexts),
            "facets": len(paper.facets),
            "transitions": len(paper.transitions),
            "claims": len(paper.claims),
        },
        "deterministic_reference_errors": errors,
        "all_references_resolve": not errors,
        "gold_context_count": None,
        "gold_claim_count": None,
        "context_recall": None,
        "claim_recall": None,
        "verification_status": "pending_independent_manual_verification",
    }


def annotation_markdown(paper, audit: dict) -> str:
    lines = [
        f"# Extraction Audit: {paper.paper.title}",
        "",
        f"Paper ID: `{paper.paper.id}`",
        "",
        "Status: independent manual verification pending. Check each item against the cited SourceBlocks and add omitted settings or findings. Do not treat this sheet as ground truth until signed off.",
        "",
        "## Complete Study Settings",
        "",
    ]
    for context in paper.contexts:
        location = context.spatial_support.name if context.spatial_support else None
        location_text = f"; location: {location}" if location else ""
        lines.append(f"- [ ] `{context.id}` {context.label}{location_text}")
        for facet in (item for item in paper.facets if item.context_id == context.id):
            lines.append(f"  - `{facet.domain}` / {facet.notion}: {facet.description}")
    lines.extend(["", "## Scientific Claims", ""])
    for claim in paper.claims:
        lines.append(
            f"- [ ] `{claim.id}` {claim.from_.concept} ({claim.from_.state}) "
            f"--{claim.relation}--> {claim.to.concept} ({claim.to.state}): {claim.description} "
            f"Evidence: {', '.join(claim.evidence_block_ids)}"
        )
    lines.extend(
        [
            "",
            "## Missing Items",
            "",
            "- [ ] No scientifically distinct study setting is missing.",
            "- [ ] No own-result Claim is missing.",
            "- [ ] Background literature has not been converted into a finding of this paper.",
            "- [ ] Null, contradictory, seasonal, scale-dependent, and sign-reversing findings are retained.",
            "",
            "Reviewer: ____________________  Date: ____________________",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a ten-paper extraction audit packet.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    papers = {paper.paper.id: paper for paper in load_shared_corpus(args.source_root)}
    missing = [paper_id for paper_id in SELECTED_PAPERS if paper_id not in papers]
    if missing:
        raise ValueError(f"Selected papers are absent from the shared corpus: {missing}")

    args.output.mkdir(parents=True, exist_ok=True)
    annotation_dir = args.output / "annotation_sheets"
    annotation_dir.mkdir(exist_ok=True)
    audits = []
    for paper_id in SELECTED_PAPERS:
        paper = papers[paper_id]
        audit = audit_paper(paper)
        audits.append(audit)
        (annotation_dir / f"{paper_id}.md").write_text(annotation_markdown(paper, audit), encoding="utf-8")

    totals = {
        key: sum(item["counts"][key] for item in audits)
        for key in ("source_blocks", "contexts", "facets", "transitions", "claims")
    }
    report = {
        "status": "deterministic provenance audit complete; independent scientific recall annotation pending",
        "papers": audits,
        "totals": totals,
        "papers_with_all_references_resolved": sum(item["all_references_resolve"] for item in audits),
        "paper_count": len(audits),
    }
    (args.output / "extraction_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"paper_count": len(audits), "totals": totals, "reference_valid": report["papers_with_all_references_resolved"]}, indent=2))


if __name__ == "__main__":
    main()
