"""Convert the supplied Koppen-Geiger KMZ package to an Earth Engine GeoTIFF."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from climatekg.koppen_palette import CLASS_COLORS


def _map_png(source: Path) -> bytes:
    with zipfile.ZipFile(source) as outer:
        kmz_name = next(name for name in outer.namelist() if name.lower().endswith(".kmz"))
        with zipfile.ZipFile(io.BytesIO(outer.read(kmz_name))) as kmz:
            png_name = next(name for name in kmz.namelist() if name.endswith("KG_1986-2010.png"))
            return kmz.read(png_name)


def convert(source: Path, output: Path) -> Path:
    rendered = np.asarray(Image.open(io.BytesIO(_map_png(source))).convert("RGB"))
    if rendered.shape != (6480, 12960, 3):
        raise ValueError(f"Unexpected rendered map shape: {rendered.shape}")
    coarse = rendered[1::3, 1::3]
    if not np.array_equal(rendered, np.repeat(np.repeat(coarse, 3, axis=0), 3, axis=1)):
        raise ValueError("The source is not an exact 3x categorical rendering")

    classes = np.zeros(coarse.shape[:2], dtype=np.uint8)
    for class_id, (_, color) in enumerate(CLASS_COLORS.items(), 1):
        classes[np.all(coarse == color, axis=2)] = class_id
    unknown = np.unique(coarse[classes == 0].reshape(-1, 3), axis=0)
    if set(map(tuple, unknown.tolist())) - {(0, 0, 0)}:
        raise ValueError(f"Unexpected source colors: {unknown.tolist()}")

    output.parent.mkdir(parents=True, exist_ok=True)
    height, width = classes.shape
    with rasterio.open(
        output, "w", driver="GTiff", width=width, height=height, count=1,
        dtype="uint8", crs="EPSG:4326", transform=from_bounds(-180, -90, 180, 90, width, height),
        nodata=0, compress="deflate", predictor=2, tiled=True, blockxsize=256, blockysize=256,
    ) as dataset:
        dataset.write(classes, 1)
        dataset.set_band_description(1, "class")
        dataset.update_tags(
            source="Global_1986-2010_KG_5m.kmz.zip",
            classes=json.dumps({index: name for index, name in enumerate(CLASS_COLORS, 1)}),
        )

    manifest = {
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_rendered_dimensions": [12960, 6480],
        "categorical_dimensions": [width, height],
        "resolution": "5 arc minutes",
        "nodata": 0,
        "classes": [{"id": index, "name": name, "rgb": list(color)} for index, (name, color) in enumerate(CLASS_COLORS.items(), 1)],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(convert(args.source, args.output))


if __name__ == "__main__":
    main()
