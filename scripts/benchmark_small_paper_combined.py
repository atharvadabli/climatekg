from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from climatekg.config import OUTPUT_ROOT, PIPELINE
from climatekg.models import Paper, SourceBlock
from climatekg.small_paper import cleaned_paper_blocks, combined_extraction_token_count, extract_small_paper
from climatekg.ollama import OllamaClient
from climatekg.utils import token_count, write_json


LEVELS = ("no", "low", "medium", "high")


def _load_paper(paper_dir: Path) -> tuple[Paper, list[SourceBlock]]:
    blocks = [
        SourceBlock.model_validate_json(line)
        for line in (paper_dir / "blocks" / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    final_path = paper_dir / "final" / "final_paper.json"
    if not final_path.exists():
        raise FileNotFoundError(f"paper metadata not found: {final_path}")
    final = json.loads(final_path.read_text(encoding="utf-8"))
    return Paper.model_validate(final["paper"]), blocks


def _raw_metrics(profile_dir: Path) -> dict[str, Any]:
    metrics_path = next((profile_dir / "extraction" / "small_paper").glob("*.attempt0.metrics.json"))
    raw_path = next((profile_dir / "extraction" / "small_paper").glob("*.attempt0.json"))
    request_path = next((profile_dir / "extraction" / "small_paper").glob("*.attempt0.request.json"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request_text = json.dumps(request, ensure_ascii=False)
    thinking = raw.get("message", {}).get("thinking", "")
    content = raw.get("message", {}).get("content", "")
    return {
        "llm_elapsed_seconds": metrics["elapsed_seconds"],
        "prompt_eval_count": metrics.get("prompt_eval_count"),
        "eval_count": metrics.get("eval_count"),
        "estimated_complete_request_tokens": token_count(request_text),
        "thinking_characters": len(thinking),
        "response_characters": len(content),
        "thinking_sha256": hashlib.sha256(thinking.encode("utf-8")).hexdigest(),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "request_path": str(request_path.resolve()),
        "raw_response_path": str(raw_path.resolve()),
    }


def _regime_checks(converted: dict[str, Any]) -> dict[str, bool]:
    text = json.dumps(converted, ensure_ascii=False).lower()
    return {
        "mentions_dry_regime": "dry" in text or "drier" in text,
        "mentions_wet_regime": "wet" in text or "wetter" in text,
        "mentions_day_or_afternoon": "day" in text or "afternoon" in text,
        "mentions_night_or_morning": "night" in text or "morning" in text,
    }


def run(paper_id: str, output_root: Path, replace: bool, levels: tuple[str, ...] = LEVELS) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    if not output_root.is_relative_to(OUTPUT_ROOT.resolve()):
        raise ValueError(f"output root must remain inside {OUTPUT_ROOT.resolve()}")
    paper_dir = Path("climatekg/runtime/data/papers") / paper_id
    paper, blocks = _load_paper(paper_dir)
    rows = []
    for level in levels:
        profile_dir = output_root / level
        if replace and profile_dir.exists():
            shutil.rmtree(profile_dir)
        stage = PIPELINE["ollama"]["stages"]["small_paper_extraction"]
        original = stage["thinking"]
        stage["thinking"] = level
        started = time.perf_counter()
        error: Exception | None = None
        try:
            contexts, facets, transitions, claims, ambiguities, _ = extract_small_paper(paper, blocks, profile_dir, OllamaClient())
        except Exception as exc:
            error = exc
        finally:
            stage["thinking"] = original
        elapsed = time.perf_counter() - started
        row: dict[str, Any] = {
            "paper_id": paper_id,
            "paper_title": paper.title,
            "thinking": level,
            "cleaned_paper_tokens": combined_extraction_token_count(blocks),
            "cleaned_block_count": len(cleaned_paper_blocks(blocks)),
            "wall_elapsed_seconds": elapsed,
            **_raw_metrics(profile_dir),
        }
        if error is None:
            converted = json.loads((profile_dir / "extraction" / "small_paper" / "converted.json").read_text(encoding="utf-8"))
            row.update({
                "status": "complete",
                "contexts": len(contexts),
                "facets": len(facets),
                "transitions": len(transitions),
                "claims": len(claims),
                "ambiguities": ambiguities,
                "regime_checks": _regime_checks(converted),
            })
        else:
            structured_path = profile_dir / "extraction" / "small_paper" / "schema_validated.json"
            if not structured_path.exists():
                structured_path = profile_dir / "extraction" / "small_paper" / "validated.json"
            structured = json.loads(structured_path.read_text(encoding="utf-8")) if structured_path.exists() else {}
            row.update({
                "status": "failed_validation",
                "error": {"type": type(error).__name__, "message": str(error)},
                "contexts": len(structured.get("contexts", [])),
                "facets": len(structured.get("facets", [])),
                "transitions": len(structured.get("transitions", [])),
                "claims": len(structured.get("claims", [])),
                "ambiguities": structured.get("ambiguities", []),
                "regime_checks": _regime_checks(structured),
            })
        write_json(profile_dir / "benchmark.json", row)
        rows.append(row)
    write_json(output_root / "benchmark.json", rows)
    _write_markdown(output_root / "BENCHMARK.md", rows)
    return rows


def _write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Small-paper combined extraction benchmark",
        "",
        f"Paper: `{rows[0]['paper_id']}` - {rows[0]['paper_title']}",
        "",
        f"Cleaned paper input: {rows[0]['cleaned_paper_tokens']} estimated tokens across {rows[0]['cleaned_block_count']} non-reference SourceBlocks.",
        "",
        "| Thinking | Status | LLM seconds | Request tokens (estimate) | Contexts | Facets | Transitions | Claims | Thinking chars |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['thinking']} | {row['status']} | {row['llm_elapsed_seconds']:.2f} | {row['estimated_complete_request_tokens']} | "
            f"{row['contexts']} | {row['facets']} | {row['transitions']} | {row['claims']} | {row['thinking_characters']} |"
        )
    lines.extend(["", "## Regime checks", ""])
    for row in rows:
        checks = ", ".join(f"{name}={'yes' if passed else 'no'}" for name, passed in row["regime_checks"].items())
        lines.append(f"- `{row['thinking']}`: {checks}")
        if row["status"] != "complete":
            lines.append(f"- `{row['thinking']}` validation failure: {row['error']['message']}")
    lines.extend([
        "",
        "These lexical checks only confirm that the known regimes appear somewhere in the structured output. Scientific review of the context hierarchy, claim scope, evidence role, and smallest sufficient evidence remains necessary.",
        "",
        "Each profile directory contains the exact request JSON, raw Ollama response including `message.thinking`, validated combined object, converted graph objects, and timing metrics.",
        "",
        "## Response hashes",
        "",
    ])
    for row in rows:
        lines.append(f"- `{row['thinking']}` thinking: `{row['thinking_sha256']}`; content: `{row['content_sha256']}`")
    lines.extend([
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", default="P000006")
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT / "small_paper_combined_v3_p000006_20260829")
    parser.add_argument("--levels", nargs="+", choices=LEVELS, default=list(LEVELS))
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    run(args.paper_id, args.output_root, args.replace, tuple(args.levels))


if __name__ == "__main__":
    main()
