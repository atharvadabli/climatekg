from __future__ import annotations

import argparse
import json
from pathlib import Path

import pypdfium2 as pdfium


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--max-pages", type=int)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(args.pdf)
    pages = []
    page_count = min(len(document), args.max_pages) if args.max_pages else len(document)
    for index in range(page_count):
        page = document[index]
        image = page.render(scale=args.dpi / 72).to_pil().convert("RGB")
        path = args.output_dir / f"page_{index + 1:04d}.png"
        image.save(path, format="PNG", optimize=False)
        pages.append({"page": index + 1, "path": str(path.resolve()), "width": image.width, "height": image.height})
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({"renderer": "PDFium", "dpi": args.dpi, "page_count": len(pages), "pages": pages}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
