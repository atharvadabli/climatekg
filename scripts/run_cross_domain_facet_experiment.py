from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from climatekg.config import PIPELINE
from climatekg.extract import extract_facets, permanent_map
from climatekg.extraction_models import PaperMap
from climatekg.models import FinalPaper, SourceBlock
from climatekg.ollama import OllamaClient
from climatekg.utils import write_json


def load_blocks(paper_dir: Path) -> list[SourceBlock]:
    blocks = [
        SourceBlock.model_validate_json(line)
        for line in (paper_dir / "blocks" / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    embeddings = json.loads((paper_dir / "blocks" / "block_embeddings.json").read_text(encoding="utf-8"))
    for block in blocks:
        block.embedding = embeddings.get(block.id)
    return blocks


def summarize(facets: list[object]) -> dict[str, object]:
    domains = Counter(facet.domain for facet in facets)
    return {
        "count": len(facets),
        "domain_counts": dict(sorted(domains.items())),
        "spatial_configuration": [
            {
                "id": facet.id,
                "context_id": facet.context_id,
                "notion": facet.notion,
                "description": facet.description,
                "evidence_block_ids": facet.evidence_block_ids,
            }
            for facet in facets
            if facet.domain == "spatial_configuration"
        ],
    }


def load_baseline_bundles(source_dir: Path, blocks: list[SourceBlock]) -> dict[str, list[SourceBlock]]:
    block_by_id = {block.id: block for block in blocks}
    bundles = {}
    facets_dir = source_dir / "extraction" / "facets"
    for context_dir in facets_dir.iterdir():
        envelope_path = next(context_dir.glob("*.envelope.json"))
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        bundles[context_dir.name] = [block_by_id[block_id] for block_id in envelope["input_block_ids"]]
    return bundles


def run_paper(
    source_root: Path,
    output_root: Path,
    paper_id: str,
    client: OllamaClient,
    context_ids: set[str] | None,
    reuse_baseline_bundles: bool,
) -> dict[str, object]:
    source_dir = source_root / paper_id
    output_dir = output_root / paper_id
    final = FinalPaper.model_validate_json((source_dir / "final" / "final_paper.json").read_text(encoding="utf-8"))
    mapped = PaperMap.model_validate_json((source_dir / "extraction" / "map" / "paper_map.json").read_text(encoding="utf-8"))
    blocks = load_blocks(source_dir)
    contexts, _, map_meta = permanent_map(final.paper, mapped)
    bundles = load_baseline_bundles(source_dir, blocks) if reuse_baseline_bundles else None
    facets, hints = extract_facets(
        final.paper,
        mapped,
        contexts,
        map_meta,
        blocks,
        output_dir,
        client,
        evidence_bundles=bundles,
        only_context_ids=context_ids,
    )
    write_json(output_dir / "facets.json", [facet.model_dump(mode="json") for facet in facets])
    result = {
        "paper_id": paper_id,
        "title": final.paper.title,
        "baseline": summarize(final.facets),
        "candidate": summarize(facets),
        "hints": hints,
    }
    write_json(output_dir / "comparison.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Facet extraction on fixed paper maps and evidence bundles.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--paper-id", action="append", required=True)
    parser.add_argument("--context-id", action="append")
    parser.add_argument("--fresh-bundles", action="store_true")
    parser.add_argument("--thinking", choices=("no", "low", "medium"), default="no")
    args = parser.parse_args()

    PIPELINE["ollama"]["stages"]["facet_extraction"]["thinking"] = args.thinking
    client = OllamaClient()
    context_ids = set(args.context_id) if args.context_id else None
    results = [
        run_paper(
            args.source_root,
            args.output_root,
            paper_id,
            client,
            context_ids,
            reuse_baseline_bundles=not args.fresh_bundles,
        )
        for paper_id in args.paper_id
    ]
    write_json(args.output_root / "comparison_summary.json", results)
    for result in results:
        baseline = result["baseline"]
        candidate = result["candidate"]
        print(
            f"{result['paper_id']}: facets {baseline['count']} -> {candidate['count']}; "
            f"spatial {len(baseline['spatial_configuration'])} -> {len(candidate['spatial_configuration'])}"
        )


if __name__ == "__main__":
    main()
