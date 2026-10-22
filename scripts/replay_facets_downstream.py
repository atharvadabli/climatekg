from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from climatekg.canonicalize import canonicalize_claim_states
from climatekg.consolidate import consolidate_paper
from climatekg.embeddings import embed_paper
from climatekg.extract import extract_claims, permanent_map
from climatekg.extraction_models import PaperMap
from climatekg.indexer import current_prompt_versions
from climatekg.models import Facet, FinalPaper, SourceBlock
from climatekg.ollama import OllamaClient
from climatekg.reconcile import reconcile_contexts
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay staged indexing downstream of a fixed Facet extraction.")
    parser.add_argument("--source-paper-dir", type=Path, required=True)
    parser.add_argument("--experiment-paper-dir", type=Path, required=True)
    args = parser.parse_args()

    source_final = FinalPaper.model_validate_json(
        (args.source_paper_dir / "final" / "final_paper.json").read_text(encoding="utf-8")
    )
    mapped = PaperMap.model_validate_json(
        (args.source_paper_dir / "extraction" / "map" / "paper_map.json").read_text(encoding="utf-8")
    )
    blocks = load_blocks(args.source_paper_dir)
    contexts, transitions, _ = permanent_map(source_final.paper, mapped)
    facets = [
        Facet.model_validate(item)
        for item in json.loads((args.experiment_paper_dir / "facets.json").read_text(encoding="utf-8"))
    ]
    client = OllamaClient()

    claims, claim_hints = extract_claims(
        source_final.paper,
        mapped,
        contexts,
        transitions,
        facets,
        blocks,
        args.experiment_paper_dir,
        client,
    )
    contexts, facets, claims, unresolved = reconcile_contexts(
        source_final.paper,
        contexts,
        transitions,
        facets,
        claims,
        claim_hints,
        blocks,
        args.experiment_paper_dir,
        client,
    )
    contexts, facets, transitions, claims, warnings = consolidate_paper(
        source_final.paper,
        contexts,
        facets,
        transitions,
        claims,
        blocks,
        args.experiment_paper_dir,
        client,
    )
    unresolved.extend({"type": "consolidation_conflict", "value": value} for value in warnings)
    states = canonicalize_claim_states(claims)
    context_texts = embed_paper(client, blocks, contexts, facets, transitions, claims, states)
    for context_id, value in context_texts.items():
        target = args.experiment_paper_dir / "final" / "context_retrieval_text" / f"{context_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")

    evidence_links = [
        {"object_id": item.id, "source_block_id": block_id}
        for items in (contexts, facets, transitions, claims)
        for item in items
        for block_id in item.evidence_block_ids
    ]
    final = FinalPaper(
        paper=source_final.paper,
        source_blocks=blocks,
        contexts=contexts,
        facets=facets,
        transitions=transitions,
        claims=claims,
        states=states,
        evidence_links=evidence_links,
        unresolved_conflicts=unresolved,
        metadata={
            **source_final.metadata,
            "prompt_versions": current_prompt_versions(False),
            "controlled_replay": "fixed_map_cross_domain_facets",
            "enrichment": "not_repeated; reported Facets only",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    write_json(args.experiment_paper_dir / "final" / "final_paper.json", final.model_dump(by_alias=True))
    write_json(
        args.experiment_paper_dir / "downstream_summary.json",
        {
            "paper_id": final.paper.id,
            "contexts": len(contexts),
            "facets": len(facets),
            "transitions": len(transitions),
            "claims": len(claims),
            "states": len(states),
            "unresolved": unresolved,
        },
    )
    print(json.dumps(json.loads((args.experiment_paper_dir / "downstream_summary.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
