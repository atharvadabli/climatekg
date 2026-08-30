"""Export finalized ClimateKG SourceBlocks as a shared baseline corpus."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SKIP_SECTIONS = {"references", "bibliography", "acknowledgements", "acknowledgments"}


@dataclass(frozen=True)
class CorpusPaper:
    namespace: str
    artifact: Path
    data: dict[str, Any]


def _identity(data: dict[str, Any]) -> str:
    paper = data["paper"]
    doi = str(paper.get("doi") or "").strip().lower()
    title = re.sub(r"\W+", " ", str(paper.get("title") or "").lower()).strip()
    return f"doi:{doi}" if doi else f"title:{title}"


def discover_papers(roots: Iterable[Path]) -> list[CorpusPaper]:
    seen: set[str] = set()
    papers: list[CorpusPaper] = []
    for root_index, root in enumerate(roots, start=1):
        paths = sorted(root.glob("data/*/final/final_paper.json"))
        if not paths and (root / "final" / "final_paper.json").exists():
            paths = [root / "final" / "final_paper.json"]
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            identity = _identity(data)
            if identity in seen:
                continue
            seen.add(identity)
            papers.append(CorpusPaper(f"R{root_index}_{data['paper']['id']}", path, data))
    return papers


def usable_blocks(data: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = []
    for block in data["source_blocks"]:
        section = " ".join(str(value) for value in block.get("section_path", [])).lower()
        if any(name in section for name in SKIP_SECTIONS):
            continue
        if block.get("block_type") in {"header", "footer", "page_number"}:
            continue
        if str(block.get("text", "")).strip():
            blocks.append(block)
    return blocks


def export_plain_rag(papers: list[CorpusPaper], output_dir: Path) -> Path:
    markdown_dir = output_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in papers:
        paper = item.data["paper"]
        markdown = markdown_dir / f"{item.namespace}.md"
        lines = [f"# {str(paper['title']).lstrip('# ').strip()}", ""]
        current_section: tuple[str, ...] = ()
        for block in usable_blocks(item.data):
            section = tuple(block.get("section_path", []))
            if section and section != current_section:
                lines.extend((f"## {' / '.join(section)}", ""))
                current_section = section
            lines.extend((f"<!-- block_id: {block['id']}; page: {block.get('page')} -->", block["text"], ""))
        markdown.write_text("\n".join(lines), encoding="utf-8")
        rows.append(
            {
                "section": "climatekg_shared_corpus",
                "paper": item.namespace,
                "pages": max((block.get("page") or 0 for block in usable_blocks(item.data)), default=0),
                "markdown": str(markdown.resolve()),
            }
        )
    manifest = output_dir / "plain_rag_manifest.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "paper", "pages", "markdown"])
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "corpus_manifest.json").write_text(
        json.dumps(
            [
                {
                    "namespace": item.namespace,
                    "paper_id": item.data["paper"]["id"],
                    "title": item.data["paper"]["title"],
                    "doi": item.data["paper"].get("doi"),
                    "artifact": str(item.artifact),
                    "source_block_count": len(usable_blocks(item.data)),
                }
                for item in papers
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest
