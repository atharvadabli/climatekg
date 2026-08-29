from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from climatekg.constants import ROUTING_TOKENIZER_ENCODING
from climatekg.models import SourceBlock
from climatekg.small_paper import combined_extraction_token_count
from climatekg.utils import sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDS = (
    "P000001", "P000002", "P000005", "P000006", "P000007",
    "P000008", "P000010", "P000013", "P000014", "P000015",
)
PRESERVED_DIRS = ("source", "parse", "clean", "blocks")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-data", type=Path, default=ROOT / "climatekg" / "runtime" / "data" / "papers")
    parser.add_argument("--input-dir", type=Path, default=Path(r"E:\Atharv\lit_200\files"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    return parser


def _source_pdf_index(input_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted(input_dir.rglob("*.pdf")):
        index.setdefault(sha256_file(path), path)
    return index


def _load_blocks(path: Path) -> list[SourceBlock]:
    return [SourceBlock.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _copy_pre_llm_artifacts(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"comparison data already exists: {target}")
    target.mkdir(parents=True)
    for name in PRESERVED_DIRS:
        source_path = source / name
        if not source_path.exists():
            raise FileNotFoundError(f"missing required prepared artifact: {source_path}")
        shutil.copytree(source_path, target / name)

    page_manifest_path = target / "parse" / "page_images.json"
    page_manifest = json.loads(page_manifest_path.read_text(encoding="utf-8"))
    image_dir = target / "parse" / "page_images"
    for page in page_manifest.get("pages", []):
        page["path"] = str((image_dir / Path(page["path"]).name).resolve())
    write_json(page_manifest_path, page_manifest)


def main() -> None:
    args = _parser().parse_args()
    output_root = args.output_root.resolve()
    ids = tuple(args.paper_ids or DEFAULT_IDS)
    pdfs = _source_pdf_index(args.input_dir.resolve())
    rows = []

    for paper_id in ids:
        source = args.source_data.resolve() / paper_id
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        digest = manifest["pdf_sha256"]
        pdf_path = pdfs.get(digest)
        if pdf_path is None:
            raise FileNotFoundError(f"source PDF for {paper_id} ({digest}) was not found under {args.input_dir}")
        blocks = _load_blocks(source / "blocks" / "blocks.jsonl")
        cleaned_tokens = combined_extraction_token_count(blocks)
        item = {
            "paper_id": paper_id,
            "filename": pdf_path.relative_to(args.input_dir.resolve()).as_posix(),
            "cleaned_non_reference_tokens": cleaned_tokens,
            "routing_tokenizer": ROUTING_TOKENIZER_ENCODING,
            "preferred_8000_token_target": cleaned_tokens <= 8000,
        }
        rows.append(item)
        for route in ("combined", "staged"):
            target = output_root / route / "data" / paper_id
            _copy_pre_llm_artifacts(source, target)
            route_manifest = dict(manifest)
            route_manifest["status"] = "source_blocks_ready"
            route_manifest.pop("counts", None)
            route_manifest.pop("failure", None)
            write_json(target / "manifest.json", route_manifest)

    corpus = [{"paper_id": row["paper_id"], "filename": row["filename"]} for row in rows]
    write_json(output_root / "corpus_manifest.json", corpus)
    write_json(output_root / "preparation_report.json", {
        "routing_tokenizer": ROUTING_TOKENIZER_ENCODING,
        "counted_content": "cleaned non-reference SourceBlocks",
        "preferred_target_tokens": 8000,
        "combined_safety_limit_tokens": 16000,
        "papers": rows,
    })
    print(json.dumps(rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
