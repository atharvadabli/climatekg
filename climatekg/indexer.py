from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonicalize import canonicalize_claim_states
from .config import PIPELINE
from .consolidate import consolidate_paper
from .embeddings import embed_paper, embed_source_blocks
from .extract import extract_claims, extract_facets, map_paper, permanent_map
from .models import FinalPaper, Paper
from .ollama import OllamaClient, stage_prompt_version
from .pdf import build_source_blocks, clean_parse, parse_pdf, register_pdf
from .reconcile import reconcile_contexts
from .utils import write_json


def _metadata(blocks: list[Any], paper_id: str, source_file: str) -> Paper:
    title_block = next((x for x in blocks if x.block_type == "title"), blocks[0])
    title = " ".join(title_block.text.split())[:500]
    sample = "\n".join(x.text for x in blocks[:30])
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", sample, re.I)
    year_match = re.search(r"\b(19|20)\d{2}\b", sample)
    return Paper(id=paper_id, title=title, source_file=source_file, doi=doi_match.group(0).rstrip(".,") if doi_match else None, year=int(year_match.group(0)) if year_match else None)


PROMPT_STAGES = (
    "paper_map",
    "section_scout",
    "map_consolidation",
    "facet_extraction",
    "claim_extraction",
    "context_reconciliation",
    "paper_consolidation",
)


def current_prompt_versions() -> dict[str, str]:
    return {stage: stage_prompt_version(stage) for stage in PROMPT_STAGES}


def _clear_derived_artifacts(paper_dir: Path, data_root: Path) -> None:
    resolved_paper = paper_dir.resolve()
    if not resolved_paper.is_relative_to(data_root.resolve()):
        raise ValueError(f"refusing to rebuild outside data root: {resolved_paper}")
    for name in ("extraction", "final"):
        target = (resolved_paper / name).resolve()
        if target.parent != resolved_paper:
            raise ValueError(f"invalid derived-artifact path: {target}")
        if target.exists():
            shutil.rmtree(target)


def index_pdf(pdf_path: Path, data_root: Path, paper_id: str, client: OllamaClient | None = None, rebuild_derived: bool = False) -> FinalPaper:
    client = client or OllamaClient()
    paper_dir, manifest = register_pdf(pdf_path, data_root, paper_id)
    final_path = paper_dir / "final" / "final_paper.json"
    if manifest.get("status") == "complete" and final_path.exists():
        cached = FinalPaper.model_validate_json(final_path.read_text(encoding="utf-8"))
        expected = current_prompt_versions()
        saved = cached.metadata.get("prompt_versions", {})
        if all(saved.get(stage) == version for stage, version in expected.items()):
            return cached
        if not rebuild_derived:
            changed = {stage: {"saved": saved.get(stage), "current": version} for stage, version in expected.items() if saved.get(stage) != version}
            raise RuntimeError(f"STALE_DERIVED_ARTIFACTS {json.dumps(changed, sort_keys=True)}; rerun with --rebuild-derived")
    if rebuild_derived:
        _clear_derived_artifacts(paper_dir, data_root)
        manifest["status"] = "registered"
        manifest.pop("counts", None)
    manifest.pop("failure", None)
    try:
        raw = parse_pdf(paper_dir / "source" / "paper.pdf", paper_dir)
        manifest["status"] = "parsed"
        write_json(paper_dir / "manifest.json", manifest)
        cleaned = clean_parse(raw, paper_dir)
        blocks = build_source_blocks(cleaned, paper_id, paper_dir, PIPELINE["blocks"]["max_block_tokens"], PIPELINE["blocks"]["target_split_tokens"])
        embed_source_blocks(client, blocks, paper_dir / "blocks" / "block_embeddings.json")
        (paper_dir / "blocks" / "blocks.jsonl").write_text("\n".join(x.model_dump_json(by_alias=True) for x in blocks) + "\n", encoding="utf-8")
        paper = _metadata(blocks, paper_id, pdf_path.name)
        manifest["status"] = "mapping"
        write_json(paper_dir / "manifest.json", manifest)
        mapped = map_paper(paper, blocks, paper_dir, client)
        contexts, transitions, map_meta = permanent_map(paper, mapped)
        write_json(paper_dir / "extraction" / "map" / "context_registry.json", map_meta)
        manifest["status"] = "extracting_facets"
        write_json(paper_dir / "manifest.json", manifest)
        facets, facet_hints = extract_facets(paper, mapped, contexts, map_meta, blocks, paper_dir, client)
        manifest["status"] = "extracting_claims"
        write_json(paper_dir / "manifest.json", manifest)
        claims, claim_hints = extract_claims(paper, mapped, contexts, transitions, facets, map_meta, blocks, paper_dir, client)
        manifest["status"] = "reconciling_contexts"
        write_json(paper_dir / "manifest.json", manifest)
        contexts, facets, claims, reconciliation_unresolved = reconcile_contexts(paper, contexts, transitions, facets, claims, facet_hints + claim_hints, blocks, paper_dir, client)
        unresolved = list(reconciliation_unresolved)
        manifest["status"] = "consolidating"
        write_json(paper_dir / "manifest.json", manifest)
        contexts, facets, transitions, claims, consolidation_warnings = consolidate_paper(paper, contexts, facets, transitions, claims, blocks, paper_dir, client)
        unresolved.extend({"type": "consolidation_conflict", "value": value} for value in consolidation_warnings)
        states = canonicalize_claim_states(claims)
        manifest["status"] = "embedding"
        write_json(paper_dir / "manifest.json", manifest)
        context_texts = embed_paper(client, blocks, contexts, facets, transitions, claims, states)
        for context_id, text in context_texts.items():
            target = paper_dir / "final" / "context_retrieval_text" / f"{context_id}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        evidence_links = [{"object_id": item.id, "source_block_id": block_id} for items in (contexts, facets, transitions, claims) for item in items for block_id in item.evidence_block_ids]
        prompt_versions = current_prompt_versions()
        final = FinalPaper(paper=paper, source_blocks=blocks, contexts=contexts, facets=facets, transitions=transitions, claims=claims, states=states, evidence_links=evidence_links, unresolved_conflicts=unresolved, metadata={"parser": "nvidia/NVIDIA-Nemotron-Parse-v1.2", "extractor_model": PIPELINE["ollama"]["model"], "embedding_model": PIPELINE["embeddings"]["model"], "embedding_dimension": PIPELINE["embeddings"]["dimension"], "prompt_versions": prompt_versions, "created_at": datetime.now(timezone.utc).isoformat()})
        write_json(paper_dir / "final" / "final_paper.json", final.model_dump(by_alias=True))
        manifest["status"] = "complete"
        manifest["counts"] = {"source_blocks": len(blocks), "contexts": len(contexts), "facets": len(facets), "transitions": len(transitions), "claims": len(claims), "states": len(states)}
        write_json(paper_dir / "manifest.json", manifest)
        return final
    except Exception as exc:
        manifest["status"] = "FAILED_PARSE" if "FAILED_PARSE" in str(exc) else "NEEDS_REVIEW"
        manifest["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(paper_dir / "manifest.json", manifest)
        raise


def load_corpus(data_root: Path) -> list[FinalPaper]:
    papers = []
    for path in sorted(data_root.glob("P*/final/final_paper.json")):
        papers.append(FinalPaper.model_validate_json(path.read_text(encoding="utf-8")))
    return papers
