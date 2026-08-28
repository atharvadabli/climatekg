from __future__ import annotations

import re
import shutil
import statistics
import json
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from .config import PIPELINE, ROOT
from .models import SourceBlock
from .utils import sha256_file, token_count, write_json


def register_pdf(pdf_path: Path, data_root: Path, paper_id: str) -> tuple[Path, dict[str, Any]]:
    digest = sha256_file(pdf_path)
    for manifest_path in data_root.glob("P*/manifest.json"):
        try:
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("pdf_sha256") == digest:
                return manifest_path.parent, manifest
        except (OSError, ValueError):
            continue
    paper_dir = data_root / paper_id
    (paper_dir / "source").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf_path, paper_dir / "source" / "paper.pdf")
    manifest = {
        "paper_id": paper_id,
        "pdf_sha256": digest,
        "status": "registered",
        "parser": "nemotron-parse-v1.2",
        "extractor_model": "qwen3.6:27b",
        "embedding_model": "qwen3-embedding:4b",
        "active_pipeline_version": "0.1",
        "warnings": [],
    }
    write_json(paper_dir / "manifest.json", manifest)
    return paper_dir, manifest


def parse_pdf(pdf_path: Path, paper_dir: Path) -> dict[str, Any]:
    """Parse exclusively with NVIDIA Nemotron-Parse v1.2; fail closed."""
    config = PIPELINE["parsing"]
    parse_dir = paper_dir / "parse"
    parse_dir.mkdir(parents=True, exist_ok=True)
    page_manifest = parse_dir / "page_images.json"
    output_path = parse_dir / "nemotron_raw.json"
    cached = _validated_parse_cache(page_manifest, output_path)
    if cached is not None:
        return cached
    render_command = [config["pdfium_python"], str(ROOT / "climatekg" / "workers" / "pdfium_render.py"), str(pdf_path), str(parse_dir / "page_images"), str(page_manifest), "--dpi", str(config["render_dpi"])]
    _run_logged(render_command, parse_dir / "renderer.log", timeout=1800)
    rendered = json.loads(page_manifest.read_text(encoding="utf-8"))
    rendered_pages = rendered.get("pages", [])
    if not rendered_pages:
        raise ValueError("FAILED_PARSE: PDFium rendered no pages")
    model_path = ROOT / config["model_path"]
    parse_command = [config["nemotron_python"], str(ROOT / "climatekg" / "workers" / "nemotron_parse.py"), str(model_path), str(page_manifest), str(output_path)]
    _run_logged(parse_command, parse_dir / "nemotron.log", timeout=7200)
    raw = json.loads(output_path.read_text(encoding="utf-8"))
    parsed_pages = raw.get("pages", [])
    rendered_numbers = [page["page"] for page in rendered_pages]
    parsed_numbers = [page["page"] for page in parsed_pages]
    if raw.get("page_count") != len(rendered_pages) or parsed_numbers != rendered_numbers:
        raw["validation_flags"] = ["PARSE_PAGE_MISMATCH"]
        write_json(output_path, raw)
        raise ValueError(
            "FAILED_PARSE: Nemotron page coverage differs from the rendered PDF "
            f"(rendered={rendered_numbers}, parsed={parsed_numbers})"
        )
    for page in raw["pages"]:
        for element in page["elements"]:
            y0, y1 = element["bbox"][1], element["bbox"][3]
            element["near_top"] = y0 <= page["height"] * 0.12
            element["near_bottom"] = y1 >= page["height"] * 0.88
    write_json(output_path, raw)
    markdown = "\n\n".join(f"<!-- PAGE {p['page']} -->\n" + "\n\n".join(e["text"] for e in p["elements"]) for p in raw["pages"])
    (parse_dir / "nemotron.md").write_text(markdown, encoding="utf-8")
    text_length = sum(len(e["text"].strip()) for p in raw["pages"] for e in p["elements"])
    flags: list[str] = []
    if not raw["pages"] or text_length < 100:
        flags.append("PARSE_EMPTY")
    if "\ufffd" in markdown:
        flags.append("PARSE_ENCODING_ERROR")
    raw["validation_flags"] = flags
    if "PARSE_EMPTY" in flags:
        raise ValueError("FAILED_PARSE: empty or corrupted PDF parse")
    return raw


def _validated_parse_cache(page_manifest: Path, output_path: Path) -> dict[str, Any] | None:
    if not page_manifest.exists() or not output_path.exists():
        return None
    try:
        rendered = json.loads(page_manifest.read_text(encoding="utf-8"))
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        rendered_pages = rendered.get("pages", [])
        parsed_pages = raw.get("pages", [])
        numbers = [page["page"] for page in rendered_pages]
        valid = (
            rendered.get("renderer") == "PDFium"
            and raw.get("parser") == "nvidia/NVIDIA-Nemotron-Parse-v1.2"
            and raw.get("page_count") == len(rendered_pages) > 0
            and [page["page"] for page in parsed_pages] == numbers
            and all(Path(page["path"]).is_file() for page in rendered_pages)
            and not raw.get("validation_flags")
        )
        return raw if valid else None
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _run_logged(command: list[str], log_path: Path, timeout: int) -> None:
    """Run an isolated parser worker and retain diagnostics beside its artifacts."""
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        log_path.write_text(
            f"COMMAND: {subprocess.list2cmdline(command)}\n\nSTDOUT:\n{exc.stdout or ''}\n\nSTDERR:\n{exc.stderr or ''}",
            encoding="utf-8",
        )
        raise RuntimeError(f"Parser worker failed; see {log_path}") from exc
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(
            f"COMMAND: {subprocess.list2cmdline(command)}\n\nTIMEOUT: {timeout}s\n\nSTDOUT:\n{exc.stdout or ''}\n\nSTDERR:\n{exc.stderr or ''}",
            encoding="utf-8",
        )
        raise RuntimeError(f"Parser worker timed out; see {log_path}") from exc
    log_path.write_text(
        f"COMMAND: {subprocess.list2cmdline(command)}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}",
        encoding="utf-8",
    )


def _header_footer_lines(raw: dict[str, Any]) -> set[str]:
    pages = raw["pages"]
    threshold = max(2, int(len(pages) * 0.6 + 0.999))
    counts: Counter[str] = Counter()
    originals: dict[str, str] = {}
    for page in pages:
        seen = set()
        for element in page["elements"]:
            if not (element["near_top"] or element["near_bottom"]):
                continue
            for line in element["text"].splitlines():
                key = re.sub(r"\d+", "#", " ".join(line.split()).lower())
                if 2 <= len(key) <= 150 and key not in seen and not line.lstrip().startswith("#"):
                    counts[key] += 1
                    originals[key] = line
                    seen.add(key)
    return {key for key, count in counts.items() if count >= threshold}


def clean_parse(raw: dict[str, Any], paper_dir: Path) -> list[dict[str, Any]]:
    repeated = _header_footer_lines(raw)
    cleaned_pages = []
    for page in raw["pages"]:
        parts = []
        for element in page["elements"]:
            if normalize_semantic_class(element.get("semantic_class")) in {"page header", "page footer"}:
                continue
            kept = []
            for line in element["text"].splitlines():
                key = re.sub(r"\d+", "#", " ".join(line.split()).lower())
                if key not in repeated:
                    kept.append(line)
            text = "\n".join(kept)
            text = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
            text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
            text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()).strip()
            if text:
                parts.append({"text": text, "semantic_class": element.get("semantic_class"), "font_size": 0, "bold": False})
        cleaned_pages.append({"page": page["page"], "elements": parts})
    markdown = "\n\n".join(f"<!-- PAGE {p['page']} -->\n" + "\n\n".join(x["text"] for x in p["elements"]) for p in cleaned_pages)
    target = paper_dir / "clean" / "cleaned.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return cleaned_pages


def _classify(text: str, first: bool, in_references: bool, font_size: float, body_size: float, bold: bool, semantic_class: str | None = None) -> str:
    stripped = text.strip()
    semantic = normalize_semantic_class(semantic_class)
    semantic_map = {"title": "title", "section header": "heading", "heading": "heading", "text": "paragraph", "list item": "list", "table": "table", "caption": "figure_caption", "formula": "equation", "footnote": "footnote", "bibliography": "reference", "page header": "other", "page footer": "other"}
    if semantic in semantic_map:
        return "reference" if in_references else semantic_map[semantic]
    if in_references:
        return "reference"
    if first:
        return "title"
    if re.fullmatch(r"(?i)(abstract|summary|introduction|methods?|materials and methods|results?|discussion|conclusions?|references|bibliography|literature cited|acknowledg(?:e)?ments?)", stripped):
        return "heading"
    if re.match(r"(?i)^(figure|fig\.)\s*\d+", stripped):
        return "figure_caption"
    if re.match(r"(?i)^table\s*\d+", stripped):
        return "table_caption" if "|" not in stripped else "table"
    if stripped.startswith(("- ", "* ", "• ")):
        return "list"
    if "|" in stripped and stripped.count("\n") >= 1:
        return "table"
    words = stripped.split()
    explicit_numbered = bool(re.match(r"^(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+[A-Za-z]", stripped))
    typographic_heading = font_size >= body_size * 1.15 or (bold and font_size >= body_size and len(words) <= 14)
    if len(stripped.splitlines()) <= 2 and len(words) <= 14 and not stripped.endswith((".", ";", ",")) and (explicit_numbered or typographic_heading):
        return "heading"
    return "paragraph"


def _split_text(text: str, max_tokens: int, target_tokens: int) -> list[tuple[str, bool]]:
    if token_count(text) <= max_tokens:
        return [(text, False)]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    pieces: list[tuple[str, bool]] = []
    current = ""
    for sentence in sentences:
        if token_count(sentence) > max_tokens:
            clauses = re.split(r"(?<=[;,])\s+", sentence)
        else:
            clauses = [sentence]
        for clause in clauses:
            hard = False
            while token_count(clause) > max_tokens:
                approx = int(max_tokens * 3.5)
                cut = clause.rfind(" ", 0, approx)
                cut = cut if cut > 0 else approx
                if current:
                    pieces.append((current.strip(), False))
                    current = ""
                pieces.append((clause[:cut].strip(), True))
                clause = clause[cut:].strip()
                hard = True
            candidate = f"{current} {clause}".strip()
            if current and token_count(candidate) > target_tokens:
                pieces.append((current.strip(), False))
                current = clause
            else:
                current = candidate
            if hard and current:
                pieces.append((current.strip(), True))
                current = ""
    if current:
        pieces.append((current.strip(), False))
    return pieces


def build_source_blocks(cleaned_pages: list[dict[str, Any]], paper_id: str, paper_dir: Path, max_tokens: int = 1500, target_tokens: int = 1100) -> list[SourceBlock]:
    blocks: list[SourceBlock] = []
    section_path: list[str] = []
    section_ordinal = 0
    paragraph_ordinal = 0
    in_references = False
    body_candidates = [x["font_size"] for page in cleaned_pages for x in page["elements"] if len(x["text"]) >= 80 and x["font_size"]]
    body_size = statistics.median(body_candidates) if body_candidates else 10.0
    for page in cleaned_pages:
        for element_data in page["elements"]:
            element = element_data["text"]
            kind = _classify(element, not blocks, in_references, element_data["font_size"], body_size, element_data["bold"], element_data.get("semantic_class"))
            if kind == "heading":
                heading = element.strip()
                if re.fullmatch(r"(?i)(references|bibliography|literature cited)", heading):
                    in_references = True
                    kind = "reference"
                else:
                    section_ordinal += 1
                    section_path = [heading]
            elif in_references:
                kind = "reference"
            paragraph_ordinal += 1
            pieces = _split_text(element, max_tokens, target_tokens)
            for index, (piece, hard) in enumerate(pieces):
                suffix = f":{chr(65 + index)}" if len(pieces) > 1 else ""
                block_id = f"{paper_id}:S{section_ordinal:02d}:P{paragraph_ordinal:04d}{suffix}"
                blocks.append(SourceBlock(id=block_id, paper_id=paper_id, order=len(blocks), page=page["page"], section_path=list(section_path), block_type=kind, text=piece, source_locator={"page": page["page"]}, oversize_hard_split=hard))
    target = paper_dir / "blocks" / "blocks.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(x.model_dump_json(by_alias=True) for x in blocks) + "\n", encoding="utf-8")
    return blocks


def normalize_semantic_class(value: str | None) -> str:
    value = re.sub(r"[_-]+", " ", value or "").strip().lower()
    return re.sub(r"\s+", " ", value)
