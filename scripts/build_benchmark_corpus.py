from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path(r"E:\Atharv\lit_200\files")
QUOTAS = {
    "afforestation": 4,
    "cropland-expansion": 1,
    "cropping-practice": 2,
    "deforestation": 9,
    "degradation-desertification": 1,
    "generic-LULCC": 8,
    "greening": 1,
    "irrigation": 4,
    "plantation": 1,
    "reservoir-tank": 2,
    "rice-paddy": 2,
    "solar-farm": 1,
    "wetland-restoration": 1,
    "wind-farm": 3,
}
LOCAL_TERMS = re.compile(
    r"temperature|cloud|precipitation|rainfall|near.surface|heat|mesoscale|regional|"
    r"irrigation|land.surface|albedo|evapotranspiration|boundary.layer|soil|monsoon|surface",
    re.IGNORECASE,
)
REMOTE_TERMS = re.compile(r"review|carbon|teleconnection|river.flow|ecosystem.service", re.IGNORECASE)


def relevance(path: Path) -> tuple[int, str]:
    stem = path.stem.replace("_", " ").replace("-", " ")
    score = len(LOCAL_TERMS.findall(stem)) - 2 * len(REMOTE_TERMS.findall(stem))
    return -score, path.as_posix().casefold()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(input_dir: Path, base_manifest: Path) -> list[dict[str, str]]:
    records = json.loads(base_manifest.read_text(encoding="utf-8"))
    selected = {Path(item["filename"]).as_posix().casefold() for item in records}
    selected_hashes = {file_sha256(input_dir / item["filename"]) for item in records}
    for category, quota in QUOTAS.items():
        candidates = sorted((input_dir / category).glob("*.pdf"), key=relevance)
        eligible = [path for path in candidates if path.relative_to(input_dir).as_posix().casefold() not in selected]
        chosen = eligible[:quota]
        reserves = iter(eligible[quota:])
        for index, path in enumerate(chosen):
            digest = file_sha256(path)
            while digest in selected_hashes:
                path = next(reserves, None)
                if path is None:
                    break
                digest = file_sha256(path)
            if path is None:
                break
            chosen[index] = path
            selected_hashes.add(digest)
        if len(chosen) != quota:
            raise RuntimeError(f"{category}: requested {quota} PDFs, found {len(chosen)}")
        for path in chosen:
            relative = path.relative_to(input_dir).as_posix()
            records.append(
                {
                    "paper_id": f"P{len(records) + 1:06d}",
                    "filename": relative,
                    "topic": category.replace("-", " "),
                }
            )
            selected.add(relative.casefold())
    if len(records) != 50:
        raise RuntimeError(f"Expected 50 papers, built {len(records)}")
    missing = [item["filename"] for item in records if not (input_dir / item["filename"]).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing corpus PDFs: {missing}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--base-manifest", type=Path, default=ROOT / "config" / "indexing_benchmark_corpus.json")
    parser.add_argument("--output", type=Path, default=ROOT / "config" / "indexing_benchmark_corpus_50.json")
    args = parser.parse_args()
    records = build_manifest(args.input_dir, args.base_manifest)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"papers": len(records), "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
