from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climatekg.canonicalize import canonicalize_claim_states
from climatekg.config import PIPELINE
from climatekg.consolidate import consolidate_paper
from climatekg.embeddings import embed_paper
from climatekg.extract import extract_claims, extract_facets, permanent_map, render_paper_map_tree
from climatekg.extraction_models import PaperMap
from climatekg.indexer import current_prompt_versions
from climatekg.models import FinalPaper
from climatekg.ollama import OllamaClient
from climatekg.reconcile import reconcile_contexts
from climatekg.utils import write_json


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay production indexing stages after an accepted paper map."
    )
    parser.add_argument("--source-final", type=Path, required=True)
    parser.add_argument("--paper-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _record(trace_path: Path, trace: dict, stage: str, started: float, **counts: int) -> None:
    trace["stages"].append(
        {"stage": stage, "elapsed_seconds": round(time.time() - started, 3), "counts": counts}
    )
    write_json(trace_path, trace)


def main() -> None:
    args = _arguments()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "stage_trace.json"
    trace = {
        "source_final": str(args.source_final.resolve()),
        "paper_map": str(args.paper_map.resolve()),
        "output_dir": str(output_dir),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": [],
    }
    write_json(trace_path, trace)

    source = FinalPaper.model_validate_json(args.source_final.read_text(encoding="utf-8"))
    mapped = PaperMap.model_validate_json(args.paper_map.read_text(encoding="utf-8"))
    paper = source.paper
    blocks = source.source_blocks
    client = OllamaClient()

    map_dir = output_dir / "extraction" / "map"
    write_json(map_dir / "paper_map.json", mapped.model_dump(by_alias=True))
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / "paper_map.tree.txt").write_text(render_paper_map_tree(mapped), encoding="utf-8")

    started = time.time()
    contexts, transitions, map_meta = permanent_map(paper, mapped)
    write_json(map_dir / "context_registry.json", map_meta)
    write_json(output_dir / "stages" / "01_contexts_transitions.json", {
        "contexts": [item.model_dump(by_alias=True) for item in contexts],
        "transitions": [item.model_dump(by_alias=True) for item in transitions],
    })
    _record(trace_path, trace, "permanent_map", started, contexts=len(contexts), transitions=len(transitions))

    started = time.time()
    facets, facet_hints = extract_facets(paper, mapped, contexts, map_meta, blocks, output_dir, client)
    write_json(output_dir / "stages" / "02_facets.json", {
        "facets": [item.model_dump(by_alias=True) for item in facets],
        "reconciliation_hints": facet_hints,
    })
    _record(trace_path, trace, "facet_extraction", started, facets=len(facets), hints=len(facet_hints))

    started = time.time()
    claims, claim_hints = extract_claims(
        paper, mapped, contexts, transitions, facets, map_meta, blocks, output_dir, client
    )
    write_json(output_dir / "stages" / "03_claims.json", {
        "claims": [item.model_dump(by_alias=True) for item in claims],
        "reconciliation_hints": claim_hints,
    })
    _record(trace_path, trace, "claim_extraction", started, claims=len(claims), hints=len(claim_hints))

    started = time.time()
    contexts, facets, claims, unresolved = reconcile_contexts(
        paper,
        contexts,
        transitions,
        facets,
        claims,
        facet_hints + claim_hints,
        blocks,
        output_dir,
        client,
    )
    write_json(output_dir / "stages" / "04_context_reconciliation.json", {
        "contexts": [item.model_dump(by_alias=True) for item in contexts],
        "facets": [item.model_dump(by_alias=True) for item in facets],
        "claims": [item.model_dump(by_alias=True) for item in claims],
        "unresolved": unresolved,
    })
    _record(trace_path, trace, "context_reconciliation", started, contexts=len(contexts), unresolved=len(unresolved))

    started = time.time()
    contexts, facets, transitions, claims, warnings = consolidate_paper(
        paper, contexts, facets, transitions, claims, blocks, output_dir, client
    )
    write_json(output_dir / "stages" / "05_consolidation.json", {
        "contexts": [item.model_dump(by_alias=True) for item in contexts],
        "facets": [item.model_dump(by_alias=True) for item in facets],
        "transitions": [item.model_dump(by_alias=True) for item in transitions],
        "claims": [item.model_dump(by_alias=True) for item in claims],
        "warnings": warnings,
    })
    _record(trace_path, trace, "paper_consolidation", started, contexts=len(contexts), facets=len(facets), transitions=len(transitions), claims=len(claims), warnings=len(warnings))

    started = time.time()
    states = canonicalize_claim_states(claims)
    write_json(output_dir / "stages" / "06_states.json", {
        "states": [item.model_dump(by_alias=True) for item in states]
    })
    _record(trace_path, trace, "state_canonicalization", started, states=len(states))

    started = time.time()
    context_texts = embed_paper(client, blocks, contexts, facets, transitions, claims, states)
    for context_id, text in context_texts.items():
        target = output_dir / "final" / "context_retrieval_text" / f"{context_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _record(trace_path, trace, "embeddings", started, contexts=len(context_texts), facets=len(facets), claims=len(claims), states=len(states))

    evidence_links = [
        {"object_id": item.id, "source_block_id": block_id}
        for items in (contexts, facets, transitions, claims)
        for item in items
        for block_id in item.evidence_block_ids
    ]
    final = FinalPaper(
        paper=paper,
        source_blocks=blocks,
        contexts=contexts,
        facets=facets,
        transitions=transitions,
        claims=claims,
        states=states,
        evidence_links=evidence_links,
        unresolved_conflicts=[*unresolved, *({"type": "consolidation_conflict", "value": value} for value in warnings)],
        metadata={
            "parser": "nvidia/NVIDIA-Nemotron-Parse-v1.2",
            "extractor_model": PIPELINE["ollama"]["model"],
            "embedding_model": PIPELINE["embeddings"]["model"],
            "embedding_dimension": PIPELINE["embeddings"]["dimension"],
            "prompt_versions": current_prompt_versions(),
            "replay_source_map": str(args.paper_map.resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    write_json(output_dir / "final" / "final_paper.json", final.model_dump(by_alias=True))
    trace["completed_at"] = datetime.now(timezone.utc).isoformat()
    trace["final_counts"] = {
        "source_blocks": len(blocks),
        "contexts": len(contexts),
        "facets": len(facets),
        "transitions": len(transitions),
        "claims": len(claims),
        "states": len(states),
    }
    write_json(trace_path, trace)


if __name__ == "__main__":
    main()
