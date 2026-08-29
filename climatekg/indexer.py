from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .canonicalize import canonicalize_claim_states
from .config import PIPELINE
from .consolidate import consolidate_paper
from .embeddings import embed_paper, embed_source_blocks
from .extract import extract_claims, extract_facets, map_paper, permanent_map
from .models import FinalPaper, Paper
from .ollama import OllamaClient, stage_prompt_version
from .pdf import build_source_blocks, clean_parse, parse_pdf, register_pdf
from .reconcile import reconcile_contexts
from .small_paper import extract_small_paper, is_combined_extraction_eligible
from .utils import write_json


def _metadata(blocks: list[Any], paper_id: str, source_file: str) -> Paper:
    config = PIPELINE["paper_metadata"]
    title_block = next((x for x in blocks if x.block_type == "title"), blocks[0])
    title = " ".join(title_block.text.split())[:config["title_max_characters"]]
    sample = "\n".join(x.text for x in blocks[:config["sample_source_blocks"]])
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


def current_prompt_versions(combined_route: bool = False) -> dict[str, str]:
    stages = (*PROMPT_STAGES, "small_paper_extraction") if combined_route else PROMPT_STAGES
    return {stage: stage_prompt_version(stage) for stage in stages}


def indexing_derivation_fingerprint(combined_route: bool) -> str:
    """Fingerprint settings that can change generated scientific artifacts."""
    parsing = {
        key: value
        for key, value in PIPELINE["parsing"].items()
        if key not in {"model_path", "nemotron_python", "pdfium_python", "render_timeout_seconds", "parse_timeout_seconds"}
    }
    ollama = {
        key: value
        for key, value in PIPELINE["ollama"].items()
        if key not in {"base_url", "request_timeout_seconds", "retry_backoff_base_seconds"}
    }
    payload = {
        "combined_route": combined_route,
        "prompt_versions": current_prompt_versions(combined_route),
        "parsing": parsing,
        "ollama": ollama,
        **{
            key: PIPELINE[key]
            for key in (
                "paper_mapping",
                "embeddings",
                "blocks",
                "source_cleaning",
                "paper_metadata",
                "section_scout",
                "evidence_retrieval",
                "consolidation",
                "enrichment",
                "canonicalization",
            )
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _write_index_timing(path: Path, report: dict[str, Any]) -> None:
    report["measured_phase_seconds"] = sum(item["elapsed_seconds"] for item in report["phases"])
    write_json(path, report)


@contextmanager
def _timed_phase(path: Path, report: dict[str, Any], name: str) -> Iterator[None]:
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    status = "complete"
    error: dict[str, str] | None = None
    try:
        yield
    except Exception as exc:
        status = "failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        phase = {
            "name": name,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started,
            "status": status,
        }
        if error:
            phase["error"] = error
        report["phases"].append(phase)
        _write_index_timing(path, report)


def index_pdf(pdf_path: Path, data_root: Path, paper_id: str, client: OllamaClient | None = None, rebuild_derived: bool = False) -> FinalPaper:
    client = client or OllamaClient()
    run_started = time.perf_counter()
    run_started_at = datetime.now(timezone.utc).isoformat()
    registration_started = time.perf_counter()
    paper_dir, manifest = register_pdf(pdf_path, data_root, paper_id)
    timing_path = paper_dir / "metrics" / "indexing_timing.json"
    timing_report: dict[str, Any] = {
        "paper_id": manifest["paper_id"],
        "source_pdf": str(pdf_path.resolve()),
        "run_started_at": run_started_at,
        "status": "running",
        "phases": [{
            "name": "paper_registration",
            "started_at": run_started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - registration_started,
            "status": "complete",
        }],
    }
    final_path = paper_dir / "final" / "final_paper.json"
    if manifest.get("status") == "complete" and final_path.exists():
        cached = FinalPaper.model_validate_json(final_path.read_text(encoding="utf-8"))
        saved = cached.metadata.get("prompt_versions", {})
        cached_combined_route = cached.metadata.get("extraction_route") == "small_paper_combined"
        expected = current_prompt_versions(cached_combined_route)
        expected_fingerprint = indexing_derivation_fingerprint(cached_combined_route)
        saved_fingerprint = cached.metadata.get("derivation_fingerprint")
        if all(saved.get(stage) == version for stage, version in expected.items()) and saved_fingerprint == expected_fingerprint:
            return cached
        if not rebuild_derived:
            changed = {stage: {"saved": saved.get(stage), "current": version} for stage, version in expected.items() if saved.get(stage) != version}
            if saved_fingerprint != expected_fingerprint:
                changed["derivation_fingerprint"] = {"saved": saved_fingerprint, "current": expected_fingerprint}
            raise RuntimeError(f"STALE_DERIVED_ARTIFACTS {json.dumps(changed, sort_keys=True)}; rerun with --rebuild-derived")
    if rebuild_derived:
        _clear_derived_artifacts(paper_dir, data_root)
        manifest["status"] = "registered"
        manifest.pop("counts", None)
    _write_index_timing(timing_path, timing_report)
    manifest.pop("failure", None)
    try:
        with _timed_phase(timing_path, timing_report, "pdf_parse_nemotron"):
            raw = parse_pdf(paper_dir / "source" / "paper.pdf", paper_dir)
        manifest["status"] = "parsed"
        write_json(paper_dir / "manifest.json", manifest)
        with _timed_phase(timing_path, timing_report, "parse_cleaning"):
            cleaned = clean_parse(raw, paper_dir)
        with _timed_phase(timing_path, timing_report, "sourceblock_generation"):
            blocks = build_source_blocks(cleaned, paper_id, paper_dir, PIPELINE["blocks"]["max_block_tokens"], PIPELINE["blocks"]["target_split_tokens"])
            (paper_dir / "blocks" / "blocks.jsonl").write_text("\n".join(x.model_dump_json(by_alias=True) for x in blocks) + "\n", encoding="utf-8")
            paper = _metadata(blocks, paper_id, pdf_path.name)
        with _timed_phase(timing_path, timing_report, "sourceblock_embeddings"):
            embed_source_blocks(client, blocks, paper_dir / "blocks" / "block_embeddings.json")
        combined_route = is_combined_extraction_eligible(blocks)
        if combined_route:
            manifest["status"] = "extracting_small_paper"
            write_json(paper_dir / "manifest.json", manifest)
            with _timed_phase(timing_path, timing_report, "small_paper_combined_extraction"):
                contexts, facets, transitions, claims, combined_ambiguities, map_meta = extract_small_paper(paper, blocks, paper_dir, client)
            facet_hints: list[str] = []
            claim_hints: list[str] = []
        else:
            manifest["status"] = "mapping"
            write_json(paper_dir / "manifest.json", manifest)
            with _timed_phase(timing_path, timing_report, "paper_mapping"):
                mapped = map_paper(paper, blocks, paper_dir, client)
            with _timed_phase(timing_path, timing_report, "permanent_context_transition_ids"):
                contexts, transitions, map_meta = permanent_map(paper, mapped)
                write_json(paper_dir / "extraction" / "map" / "context_registry.json", map_meta)
            manifest["status"] = "extracting_facets"
            write_json(paper_dir / "manifest.json", manifest)
            with _timed_phase(timing_path, timing_report, "facet_extraction"):
                facets, facet_hints = extract_facets(paper, mapped, contexts, map_meta, blocks, paper_dir, client)
            manifest["status"] = "extracting_claims"
            write_json(paper_dir / "manifest.json", manifest)
            with _timed_phase(timing_path, timing_report, "claim_extraction"):
                claims, claim_hints = extract_claims(paper, mapped, contexts, transitions, facets, map_meta, blocks, paper_dir, client)
        manifest["status"] = "reconciling_contexts"
        write_json(paper_dir / "manifest.json", manifest)
        with _timed_phase(timing_path, timing_report, "context_reconciliation"):
            contexts, facets, claims, reconciliation_unresolved = reconcile_contexts(paper, contexts, transitions, facets, claims, facet_hints + claim_hints, blocks, paper_dir, client)
            unresolved = ([{"type": "combined_extraction_ambiguity", "value": value} for value in combined_ambiguities] if combined_route else []) + list(reconciliation_unresolved)
        manifest["status"] = "consolidating"
        write_json(paper_dir / "manifest.json", manifest)
        with _timed_phase(timing_path, timing_report, "paper_consolidation"):
            contexts, facets, transitions, claims, consolidation_warnings = consolidate_paper(paper, contexts, facets, transitions, claims, blocks, paper_dir, client)
            unresolved.extend({"type": "consolidation_conflict", "value": value} for value in consolidation_warnings)
        with _timed_phase(timing_path, timing_report, "state_canonicalization"):
            states = canonicalize_claim_states(claims)
        manifest["status"] = "embedding"
        write_json(paper_dir / "manifest.json", manifest)
        with _timed_phase(timing_path, timing_report, "final_object_embeddings"):
            context_texts = embed_paper(client, blocks, contexts, facets, transitions, claims, states)
        with _timed_phase(timing_path, timing_report, "final_artifact_assembly"):
            for context_id, text in context_texts.items():
                target = paper_dir / "final" / "context_retrieval_text" / f"{context_id}.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            evidence_links = [{"object_id": item.id, "source_block_id": block_id} for items in (contexts, facets, transitions, claims) for item in items for block_id in item.evidence_block_ids]
            prompt_versions = current_prompt_versions(combined_route)
            final = FinalPaper(paper=paper, source_blocks=blocks, contexts=contexts, facets=facets, transitions=transitions, claims=claims, states=states, evidence_links=evidence_links, unresolved_conflicts=unresolved, metadata={"parser": PIPELINE["parsing"]["model"], "extractor_model": PIPELINE["ollama"]["model"], "embedding_model": PIPELINE["embeddings"]["model"], "embedding_dimension": PIPELINE["embeddings"]["dimension"], "reasoning_profile": PIPELINE["ollama"]["reasoning_profile"], "reasoning_levels": {stage: config["thinking"] for stage, config in PIPELINE["ollama"]["stages"].items()}, "extraction_route": "small_paper_combined" if combined_route else "staged", "prompt_versions": prompt_versions, "derivation_fingerprint": indexing_derivation_fingerprint(combined_route), "created_at": datetime.now(timezone.utc).isoformat()})
            write_json(paper_dir / "final" / "final_paper.json", final.model_dump(by_alias=True))
        manifest["status"] = "complete"
        manifest["counts"] = {"source_blocks": len(blocks), "contexts": len(contexts), "facets": len(facets), "transitions": len(transitions), "claims": len(claims), "states": len(states)}
        write_json(paper_dir / "manifest.json", manifest)
        timing_report["status"] = "complete"
        timing_report["finished_at"] = datetime.now(timezone.utc).isoformat()
        timing_report["wall_elapsed_seconds"] = time.perf_counter() - run_started
        _write_index_timing(timing_path, timing_report)
        return final
    except Exception as exc:
        manifest["status"] = "FAILED_PARSE" if "FAILED_PARSE" in str(exc) else "NEEDS_REVIEW"
        manifest["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(paper_dir / "manifest.json", manifest)
        timing_report["status"] = "failed"
        timing_report["finished_at"] = datetime.now(timezone.utc).isoformat()
        timing_report["wall_elapsed_seconds"] = time.perf_counter() - run_started
        timing_report["failure"] = manifest["failure"]
        _write_index_timing(timing_path, timing_report)
        raise


def load_corpus(data_root: Path) -> list[FinalPaper]:
    papers = []
    for path in sorted(data_root.glob("P*/final/final_paper.json")):
        papers.append(FinalPaper.model_validate_json(path.read_text(encoding="utf-8")))
    return papers
