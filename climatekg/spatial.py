from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import SpatialSupport


SUPPORTED_GEOMETRY_TYPES = {"Point", "Polygon", "MultiPolygon"}


def geometry_hash(geometry: dict[str, Any]) -> str:
    encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _positions(coordinates: Any) -> list[tuple[float, float]]:
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in coordinates[:2])
    ):
        return [(float(coordinates[0]), float(coordinates[1]))]
    if not isinstance(coordinates, list):
        raise ValueError("geometry coordinates must be nested arrays of numbers")
    return [position for child in coordinates for position in _positions(child)]


def validate_geojson_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    if set(geometry) != {"type", "coordinates"}:
        raise ValueError("geometry must contain only GeoJSON type and coordinates")
    geometry_type = geometry["type"]
    if geometry_type not in SUPPORTED_GEOMETRY_TYPES:
        raise ValueError(f"unsupported geometry type: {geometry_type}")
    positions = _positions(geometry["coordinates"])
    if not positions:
        raise ValueError("geometry contains no positions")
    if any(not -180 <= lon <= 180 or not -90 <= lat <= 90 for lon, lat in positions):
        raise ValueError("geometry coordinates are outside longitude/latitude bounds")
    if geometry_type == "Point" and len(positions) != 1:
        raise ValueError("Point geometry must contain one longitude/latitude position")
    return {"type": geometry_type, "coordinates": geometry["coordinates"]}


@lru_cache(maxsize=4)
def _watershed_registry(path_text: str) -> dict[str, dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"watershed registry not found: {path}")
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("watershed registry must be a GeoJSON FeatureCollection")
    registry: dict[str, dict[str, Any]] = {}
    for feature in collection.get("features", []):
        identifier = str(feature.get("properties", {}).get("wsconc", "")).strip()
        if not identifier or identifier in registry:
            raise ValueError(f"invalid or duplicate watershed identifier: {identifier!r}")
        registry[identifier] = validate_geojson_geometry(feature["geometry"])
    return registry


def _coordinate_geometry(text: str) -> dict[str, Any] | None:
    labeled = re.search(
        r"lat(?:itude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*[,; ]+\s*lon(?:gitude)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
        text,
        re.I,
    )
    if labeled:
        latitude, longitude = map(float, labeled.groups())
        return validate_geojson_geometry({"type": "Point", "coordinates": [longitude, latitude]})
    return None


def resolve_spatial_support(support: SpatialSupport, watershed_registry_path: str) -> SpatialSupport:
    """Apply the deterministic part of the specification's resolution precedence."""
    if support.geometry is not None:
        geometry = validate_geojson_geometry(support.geometry)
        kind = "point" if geometry["type"] == "Point" else support.kind
        return support.model_copy(update={"kind": kind, "geometry": geometry, "resolution": "exact"})

    point = _coordinate_geometry(support.name)
    if point is not None:
        return support.model_copy(update={"kind": "point", "geometry": point, "resolution": "exact"})

    identifiers = re.findall(r"\bC\d{2}[A-Z]{3}\d{2}\b", support.name.upper())
    if not identifiers:
        return support.model_copy(update={"geometry": None, "resolution": "unresolved"})
    registry = _watershed_registry(watershed_registry_path)
    matches = [identifier for identifier in identifiers if identifier in registry]
    if len(set(matches)) == 1:
        identifier = matches[0]
        return SpatialSupport(
            kind="watershed",
            name=identifier,
            geometry=registry[identifier],
            resolution="exact",
        )
    return support.model_copy(update={"geometry": None, "resolution": "unresolved"})
