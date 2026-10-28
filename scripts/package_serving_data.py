"""Package the prebuilt graph, baseline indexes, and map assets for deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REQUIRED_DATA = (
    "parquet_graph/manifest.json",
    "baselines/graphrag",
    "baselines/plain_rag/index",
)
REQUIRED_ASSETS = (
    "watershed_pan_india_simplified.geojson",
    "Global_1986-2010_KG_5m.kmz.zip",
)


def package(data_root: Path, assets_root: Path, output: Path) -> None:
    missing = [name for name in REQUIRED_DATA if not (data_root / name).exists()]
    missing += [name for name in REQUIRED_ASSETS if not (assets_root / name).exists()]
    if missing:
        raise ValueError(f"missing serving artifacts: {', '.join(missing)}")

    graph_manifest = json.loads((data_root / REQUIRED_DATA[0]).read_text(encoding="utf-8"))
    if graph_manifest.get("format") != "climatekg-parquet-graph":
        raise ValueError("unsupported Parquet graph manifest")

    data_files = sorted(
        path for directory in ("parquet_graph", "baselines")
        for path in (data_root / directory).rglob("*")
        if path.is_file()
    )
    asset_files = [assets_root / name for name in REQUIRED_ASSETS]
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for path in data_files:
            archive.write(path, f"data/{path.relative_to(data_root).as_posix()}")
        for path in asset_files:
            archive.write(path, f"assets/{path.name}")

    digest = hashlib.sha256()
    with output.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest.hexdigest()}  {output.name}\n", encoding="ascii"
    )
    print(f"Created {output} with {len(data_files) + len(asset_files)} files; SHA-256 {digest.hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path, help="directory containing parquet_graph/ and baselines/")
    parser.add_argument("assets_root", type=Path, help="directory containing the two map assets")
    parser.add_argument("output", type=Path, help="output ZIP path")
    args = parser.parse_args()
    package(args.data_root.resolve(), args.assets_root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
