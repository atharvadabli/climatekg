from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from climatekg.config import PIPELINE
from climatekg.earth_engine import EarthEngineBackend, EarthEngineConfigurationError
from climatekg.enrichment import derive_facets, query_facets
from climatekg.models import SpatialSupport
from climatekg.spatial import geometry_hash, resolve_spatial_support, validate_geojson_geometry


POLYGON = {
    "type": "Polygon",
    "coordinates": [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.1], [77.0, 12.0]]],
}


class FakeBackend:
    def area_sqkm(self, geometry: dict[str, Any]) -> float:
        return 123.4

    def aridity(self, geometry: dict[str, Any]) -> dict[str, Any]:
        return {"coverage": 0.95, "precipitation_mm": 600.0, "pet_mm": 1500.0}

    def climate_regime(self, geometry: dict[str, Any]) -> dict[str, Any]:
        return {"coverage": 1.0, "fractions": {"14": 0.72, "13": 0.28}}

    def wind(self, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        records = []
        for month in range(1, 13):
            u = -2.0 if month in {6, 7, 8} else 2.0
            records.append({"date": f"2000-{month:02d}", "month": month, "u": u, "v": 0.0})
        return records

    def terrain(self, geometry: dict[str, Any]) -> dict[str, Any]:
        return {"coverage": 0.99, "elevation_p10_m": 100.0, "elevation_median_m": 150.0, "elevation_p90_m": 250.0, "slope_median_deg": 4.0}

    def land_cover(self, geometry: dict[str, Any]) -> dict[str, Any]:
        return {"coverage": 0.98, "fractions": {"40": 0.7, "10": 0.25, "50": 0.05}}


class BroadRegionBackend(FakeBackend):
    def area_sqkm(self, geometry: dict[str, Any]) -> float:
        return 2_000_000.0

    def climate_regime(self, geometry: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("broad-region enrichment should stop before raster calls")


def _registry(path: Path) -> None:
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"wsconc": "C01ABC01"}, "geometry": POLYGON}],
    }), encoding="utf-8")


def test_exact_watershed_resolution(tmp_path: Path) -> None:
    registry = tmp_path / "watersheds.geojson"
    _registry(registry)
    unresolved = SpatialSupport(kind="watershed", name="watershed C01ABC01", geometry=None, resolution="unresolved")
    resolved = resolve_spatial_support(unresolved, str(registry))
    assert resolved.name == "C01ABC01"
    assert resolved.resolution == "exact"
    assert resolved.geometry == POLYGON


def test_explicit_coordinates_take_precedence_without_registry() -> None:
    unresolved = SpatialSupport(kind="unresolved", name="latitude 12.3, longitude 77.4", geometry=None, resolution="unresolved")
    resolved = resolve_spatial_support(unresolved, "missing.geojson")
    assert resolved.kind == "point"
    assert resolved.geometry == {"type": "Point", "coordinates": [77.4, 12.3]}


def test_geometry_validation_and_hash_are_deterministic() -> None:
    assert validate_geojson_geometry(POLYGON) == POLYGON
    assert geometry_hash(POLYGON) == geometry_hash({"coordinates": POLYGON["coordinates"], "type": "Polygon"})
    with pytest.raises(ValueError, match="bounds"):
        validate_geojson_geometry({"type": "Point", "coordinates": [200, 12]})


def test_shared_enrichment_builds_provenanced_facets() -> None:
    config = PIPELINE["enrichment"]
    support = SpatialSupport(kind="watershed", name="C01ABC01", geometry=POLYGON, resolution="exact")
    derived, raw, warnings = derive_facets(support, FakeBackend(), config)
    assert {item.domain for item in derived} >= {"climate", "hydrology", "atmosphere", "substrate_terrain", "land_surface"}
    assert any("P/PET is 0.400" in item.description and "semi-arid" in item.description for item in derived)
    assert len([item for item in derived if item.domain == "atmosphere"]) == 4
    assert all(item.source.geometry_hash == geometry_hash(POLYGON) for item in derived)
    assert raw["land_cover"]["fractions"]["40"] == 0.7
    assert raw["area_sqkm"] == 123.4
    assert any("Dominant 1986-2010 Koppen-Geiger" in item.description and "Csc 72.0%" in item.description for item in derived)
    assert "ENRICHMENT_CLIMATE_REGIME_NOT_CONFIGURED" not in warnings


def test_query_facet_ids_continue_after_user_facets() -> None:
    config = PIPELINE["enrichment"]
    support = SpatialSupport(kind="watershed", name="C01ABC01", geometry=POLYGON, resolution="exact")
    derived, _, _ = derive_facets(support, FakeBackend(), config)
    facets = query_facets("Q1", 2, derived)
    assert facets[0].id == "Q1_F003"
    assert all(facet.origin == "derived" and facet.source for facet in facets)


def test_large_polygon_skips_high_resolution_families_only() -> None:
    config = {
        **PIPELINE["enrichment"],
        "max_native_land_cover_pixels": 100,
        "max_native_terrain_pixels": 100,
    }
    support = SpatialSupport(kind="region", name="large domain", geometry=POLYGON, resolution="exact")
    derived, raw, warnings = derive_facets(support, FakeBackend(), config)
    assert raw["land_cover"]["status"] == "skipped"
    assert raw["terrain"]["status"] == "skipped"
    assert not any(item.notion == "land-cover composition" for item in derived)
    assert any(warning.startswith("ENRICHMENT_SKIPPED_SCALE_LIMIT:land_cover") for warning in warnings)
    assert any(warning.startswith("ENRICHMENT_SKIPPED_SCALE_LIMIT:terrain") for warning in warnings)
    assert any(item.notion == "Koppen-Geiger climate regime" for item in derived)


def test_broad_region_stops_before_raster_calls() -> None:
    config = PIPELINE["enrichment"]
    support = SpatialSupport(kind="region", name="continental domain", geometry=POLYGON, resolution="approximate")
    derived, raw, warnings = derive_facets(support, BroadRegionBackend(), config)
    assert derived == []
    assert raw["status"] == "skipped"
    assert warnings[0].startswith("ENRICHMENT_SKIPPED_BROAD_REGION")


def test_earth_engine_requires_explicit_project() -> None:
    config = PIPELINE["enrichment"]
    with pytest.raises(EarthEngineConfigurationError, match="EARTH_ENGINE_PROJECT"):
        EarthEngineBackend(None, config["datasets"], config["reference_period"])
