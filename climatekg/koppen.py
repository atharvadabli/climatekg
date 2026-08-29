"""Deterministic reader for the configured Köppen-Geiger KMZ package."""

from __future__ import annotations

import io
import zipfile
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds

from .koppen_palette import CLASS_COLORS


class KoppenRaster:
    width = 4320
    height = 2160
    transform = from_bounds(-180, -90, 180, 90, width, height)

    def __init__(self, source: str) -> None:
        self.source = Path(source)
        if not self.source.is_file():
            raise FileNotFoundError(f"Configured Köppen-Geiger source does not exist: {self.source}")

    @cached_property
    def classes(self) -> np.ndarray:
        with zipfile.ZipFile(self.source) as outer:
            kmz_name = next(name for name in outer.namelist() if name.lower().endswith(".kmz"))
            with zipfile.ZipFile(io.BytesIO(outer.read(kmz_name))) as kmz:
                png_name = next(name for name in kmz.namelist() if name.endswith("KG_1986-2010.png"))
                rendered = np.asarray(Image.open(io.BytesIO(kmz.read(png_name))).convert("RGB"))
        if rendered.shape != (self.height * 3, self.width * 3, 3):
            raise ValueError(f"Unexpected Köppen-Geiger map shape: {rendered.shape}")
        coarse = rendered[1::3, 1::3]
        if any(
            not np.array_equal(rendered[row_offset::3, column_offset::3], coarse)
            for row_offset in range(3)
            for column_offset in range(3)
        ):
            raise ValueError("The Köppen-Geiger source is not an exact 3x categorical rendering")
        classes = np.zeros((self.height, self.width), dtype=np.uint8)
        for class_id, color in enumerate(CLASS_COLORS.values(), 1):
            classes[np.all(coarse == color, axis=2)] = class_id
        unknown = np.unique(coarse[classes == 0].reshape(-1, 3), axis=0)
        if set(map(tuple, unknown.tolist())) - {(0, 0, 0)}:
            raise ValueError(f"Unexpected Köppen-Geiger colors: {unknown.tolist()}")
        return classes

    def summarize(self, geometry: dict[str, Any]) -> dict[str, Any]:
        if geometry["type"] == "Point":
            longitude, latitude = geometry["coordinates"]
            column = min(self.width - 1, max(0, int((longitude + 180.0) * 12.0)))
            row = min(self.height - 1, max(0, int((90.0 - latitude) * 12.0)))
            value = int(self.classes[row, column])
            return {"coverage": 1.0 if value else 0.0, "fractions": {} if not value else {str(value): 1.0}}

        selected = ~geometry_mask([geometry], out_shape=self.classes.shape, transform=self.transform, all_touched=False)
        selected_count = int(selected.sum())
        if selected_count == 0:
            return {"coverage": 0.0, "fractions": {}}
        valid = selected & (self.classes != 0)
        lat_edges = np.linspace(90.0, -90.0, self.height + 1)
        row_areas = np.abs(np.sin(np.radians(lat_edges[:-1])) - np.sin(np.radians(lat_edges[1:])))
        weights = np.broadcast_to(row_areas[:, None], self.classes.shape)
        selected_area = float(weights[selected].sum())
        valid_area = float(weights[valid].sum())
        fractions = {
            str(class_id): float(weights[valid & (self.classes == class_id)].sum()) / valid_area
            for class_id in np.unique(self.classes[valid])
        }
        return {"coverage": valid_area / selected_area, "fractions": fractions}
