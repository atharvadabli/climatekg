from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .earth_engine import EarthEngineBackend
from .models import Facet, ProvenanceSource, QueryFacet, SpatialSupport
from .spatial import geometry_hash


LAND_COVER_CLASSES = {
    "10": "tree cover",
    "20": "shrubland",
    "30": "grassland",
    "40": "cropland",
    "50": "built-up land",
    "60": "bare or sparse vegetation",
    "70": "snow and ice",
    "80": "permanent water",
    "90": "herbaceous wetland",
    "95": "mangroves",
    "100": "moss and lichen",
}

KOPPEN_CLASSES = {
    str(index): name
    for index, name in enumerate(
        ("Af", "Am", "As", "Aw", "BSh", "BSk", "BWh", "BWk", "Cfa", "Cfb", "Cfc", "Csa", "Csb", "Csc", "Cwa", "Cwb", "Cwc", "Dfa", "Dfb", "Dfc", "Dfd", "Dsa", "Dsb", "Dsc", "Dsd", "Dwa", "Dwb", "Dwc", "Dwd", "EF", "ET"),
        1,
    )
}


@dataclass(frozen=True)
class DerivedFacet:
    domain: str
    notion: str
    description: str
    source: ProvenanceSource


def _source(config: dict[str, Any], family: str, geometry: dict[str, Any], method: str) -> ProvenanceSource:
    dataset = config["datasets"][family]
    return ProvenanceSource(
        type="dataset",
        dataset=dataset["id"],
        version=dataset["version"],
        method=f"{method}; {config['algorithm_version']}",
        temporal_window=dataset.get("temporal_window")
        or (config["reference_period"]["label"] if family in {"aridity", "wind"} else None),
        geometry_hash=geometry_hash(geometry),
    )


def aridity_facet(raw: dict[str, Any], config: dict[str, Any], geometry: dict[str, Any]) -> DerivedFacet | None:
    precipitation, pet = raw.get("precipitation_mm"), raw.get("pet_mm")
    if precipitation is None or pet is None or pet <= 0:
        return None
    index = precipitation / pet
    label = (
        "hyper-arid" if index < 0.05 else
        "arid" if index < 0.20 else
        "semi-arid" if index < 0.50 else
        "dry sub-humid" if index < 0.65 else
        "humid"
    )
    period = config["reference_period"]["label"]
    return DerivedFacet(
        domain="hydrology",
        notion="aridity regime",
        description=f"For {period}, area-weighted mean annual precipitation is {precipitation:.1f} mm and PET is {pet:.1f} mm; P/PET is {index:.3f}, classified as {label}.",
        source=_source(config, "aridity", geometry, "area-weighted annual precipitation divided by area-weighted annual PET"),
    )


def _wind_summary(records: list[dict[str, Any]]) -> dict[str, float] | None:
    if not records:
        return None
    u_bar = sum(item["u"] for item in records) / len(records)
    v_bar = sum(item["v"] for item in records) / len(records)
    mean_speed = sum(math.hypot(item["u"], item["v"]) for item in records) / len(records)
    vector_speed = math.hypot(u_bar, v_bar)
    wind_to = (math.degrees(math.atan2(u_bar, v_bar)) + 360.0) % 360.0
    return {
        "u_bar": u_bar,
        "v_bar": v_bar,
        "mean_speed": mean_speed,
        "vector_speed": vector_speed,
        "persistence": vector_speed / max(mean_speed, 1e-12),
        "wind_from_deg": (wind_to + 180.0) % 360.0,
    }


def _compass(degrees: float) -> str:
    labels = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")
    return labels[int((degrees + 22.5) // 45) % 8]


def _angle_difference(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _materially_different(summaries: list[dict[str, float]]) -> bool:
    for index, left in enumerate(summaries):
        for right in summaries[index + 1:]:
            speeds = sorted((left["mean_speed"], right["mean_speed"]))
            if (
                _angle_difference(left["wind_from_deg"], right["wind_from_deg"]) >= 45.0
                or abs(left["persistence"] - right["persistence"]) >= 0.25
                or (speeds[0] > 0 and speeds[1] / speeds[0] >= 1.5)
            ):
                return True
    return False


def wind_facets(records: list[dict[str, Any]], config: dict[str, Any], geometry: dict[str, Any]) -> list[DerivedFacet]:
    annual = _wind_summary(records)
    if annual is None:
        return []
    seasonal = []
    for name, months in config["seasons"].items():
        summary = _wind_summary([item for item in records if item["month"] in months])
        if summary is not None:
            seasonal.append((name, summary))
    selected = seasonal if _materially_different([summary for _, summary in seasonal]) else [("annual", annual)]
    threshold = config["wind_directional_persistence_threshold"]
    source = _source(config, "wind", geometry, "spatial mean u/v per monthly time step followed by temporal vector statistics")
    facets = []
    for period, summary in selected:
        persistence = summary["persistence"]
        if persistence < threshold:
            description = f"{period} 10 m flow is directionally variable: mean speed {summary['mean_speed']:.2f} m/s and directional persistence {persistence:.2f}."
        else:
            description = f"{period} 10 m flow is predominantly from the {_compass(summary['wind_from_deg'])} ({summary['wind_from_deg']:.1f} degrees): mean speed {summary['mean_speed']:.2f} m/s and directional persistence {persistence:.2f}."
        facets.append(DerivedFacet("atmosphere", f"{period} background wind regime", description, source))
    return facets


def terrain_facet(raw: dict[str, Any], config: dict[str, Any], geometry: dict[str, Any]) -> DerivedFacet | None:
    required = ("elevation_p10_m", "elevation_median_m", "elevation_p90_m", "slope_median_deg")
    if any(raw.get(key) is None for key in required):
        return None
    relief = float(raw["elevation_p90_m"]) - float(raw["elevation_p10_m"])
    return DerivedFacet(
        domain="substrate_terrain",
        notion="terrain setting",
        description=f"Median elevation is {raw['elevation_median_m']:.1f} m; elevation p10-p90 is {raw['elevation_p10_m']:.1f}-{raw['elevation_p90_m']:.1f} m, giving {relief:.1f} m relief; median slope is {raw['slope_median_deg']:.1f} degrees.",
        source=_source(config, "terrain", geometry, "polygon elevation and slope percentiles"),
    )


def land_cover_facet(raw: dict[str, Any], config: dict[str, Any], geometry: dict[str, Any]) -> DerivedFacet | None:
    fractions = raw.get("fractions", {})
    if not fractions:
        return None
    ordered = sorted(fractions.items(), key=lambda item: (-item[1], item[0]))
    retained = [item for item in ordered if item[1] >= 0.05]
    if ordered[0] not in retained:
        retained.insert(0, ordered[0])
    parts = [f"{LAND_COVER_CLASSES.get(code, f'class {code}')} {fraction * 100:.1f}%" for code, fraction in retained]
    return DerivedFacet(
        domain="land_surface",
        notion="land-cover composition",
        description="Area-weighted 2021 land-cover composition: " + "; ".join(parts) + ".",
        source=_source(config, "land_cover", geometry, "native-resolution pixel-area class fractions"),
    )


def climate_regime_facet(raw: dict[str, Any], config: dict[str, Any], geometry: dict[str, Any]) -> DerivedFacet | None:
    fractions = raw.get("fractions", {})
    if not fractions:
        return None
    ordered = sorted(fractions.items(), key=lambda item: (-item[1], item[0]))
    retained: list[tuple[str, float]] = []
    cumulative = 0.0
    for item in ordered:
        retained.append(item)
        cumulative += item[1]
        if cumulative >= 0.80 or len(retained) == 3:
            break
    parts = [f"{KOPPEN_CLASSES.get(code, f'class {code}')} {fraction * 100:.1f}%" for code, fraction in retained]
    qualifier = "Dominant" if ordered[0][1] >= 0.60 else "Mixed"
    return DerivedFacet(
        domain="climate",
        notion="Koppen-Geiger climate regime",
        description=f"{qualifier} 1986-2010 Koppen-Geiger classes by pixel area: " + "; ".join(parts) + ".",
        source=_source(config, "climate_regime", geometry, "native 5-arc-minute categorical pixel-area class fractions"),
    )


def derive_facets(support: SpatialSupport, backend: EarthEngineBackend, config: dict[str, Any]) -> tuple[list[DerivedFacet], dict[str, Any], list[str]]:
    if support.geometry is None:
        return [], {}, ["ENRICHMENT_SKIPPED_UNRESOLVED_SPATIAL_SUPPORT"]
    geometry = support.geometry
    area_sqkm = backend.area_sqkm(geometry)
    area_limit = float(config["max_local_enrichment_area_sqkm"])
    if geometry["type"] != "Point" and area_sqkm > area_limit:
        warning = f"ENRICHMENT_SKIPPED_BROAD_REGION:area_sqkm={area_sqkm:.1f}:threshold={area_limit:.1f}"
        return [], {
            "area_sqkm": area_sqkm,
            "status": "skipped",
            "reason": "broad_region_area_limit",
            "area_threshold_sqkm": area_limit,
        }, [warning]
    land_cover_scale = float(config["datasets"]["land_cover"]["scale_m"])
    terrain_scale = float(config["datasets"]["terrain"]["scale_m"])
    estimated_land_cover_pixels = area_sqkm * 1_000_000.0 / (land_cover_scale ** 2)
    estimated_terrain_pixels = area_sqkm * 1_000_000.0 / (terrain_scale ** 2)
    land_cover_limit = int(config["max_native_land_cover_pixels"])
    terrain_limit = int(config["max_native_terrain_pixels"])
    skip_land_cover = geometry["type"] != "Point" and estimated_land_cover_pixels > land_cover_limit
    skip_terrain = geometry["type"] != "Point" and estimated_terrain_pixels > terrain_limit
    land_cover_raw = (
        {
            "status": "skipped",
            "reason": "native_pixel_scale_limit",
            "estimated_pixels": round(estimated_land_cover_pixels),
            "pixel_threshold": land_cover_limit,
            "coverage": 0.0,
            "fractions": {},
        }
        if skip_land_cover else backend.land_cover(geometry)
    )
    terrain_raw = (
        {
            "status": "skipped",
            "reason": "native_pixel_scale_limit",
            "estimated_pixels": round(estimated_terrain_pixels),
            "pixel_threshold": terrain_limit,
            "coverage": 0.0,
        }
        if skip_terrain else backend.terrain(geometry)
    )
    raw = {
        "area_sqkm": area_sqkm,
        "climate_regime": backend.climate_regime(geometry),
        "aridity": backend.aridity(geometry),
        "wind": backend.wind(geometry),
        "terrain": terrain_raw,
        "land_cover": land_cover_raw,
    }
    minimum = config["min_valid_polygon_coverage"]
    warnings: list[str] = []
    facets: list[DerivedFacet] = []
    if skip_land_cover:
        warnings.append(
            f"ENRICHMENT_SKIPPED_SCALE_LIMIT:land_cover:estimated_pixels={round(estimated_land_cover_pixels)}:threshold={land_cover_limit}"
        )
    if skip_terrain:
        warnings.append(
            f"ENRICHMENT_SKIPPED_SCALE_LIMIT:terrain:estimated_pixels={round(estimated_terrain_pixels)}:threshold={terrain_limit}"
        )
    for family in ("climate_regime", "aridity", "terrain", "land_cover"):
        if raw[family].get("status") == "skipped":
            continue
        if raw[family].get("coverage", 0.0) < minimum:
            warnings.append(f"ENRICHMENT_LOW_COVERAGE:{family}")
    if raw["aridity"].get("coverage", 0.0) >= minimum:
        facet = aridity_facet(raw["aridity"], config, geometry)
        if facet:
            facets.append(facet)
    if raw["climate_regime"].get("coverage", 0.0) >= minimum:
        facet = climate_regime_facet(raw["climate_regime"], config, geometry)
        if facet:
            facets.append(facet)
    facets.extend(wind_facets(raw["wind"], config, geometry))
    if raw["terrain"].get("coverage", 0.0) >= minimum:
        facet = terrain_facet(raw["terrain"], config, geometry)
        if facet:
            facets.append(facet)
    if raw["land_cover"].get("coverage", 0.0) >= minimum:
        facet = land_cover_facet(raw["land_cover"], config, geometry)
        if facet:
            facets.append(facet)
    if not skip_land_cover:
        warnings.append("ENRICHMENT_LAND_COVER_CONFIGURATION_METRICS_NOT_IMPLEMENTED")
    return facets, raw, warnings


def query_facets(query_id: str, existing_count: int, derived: list[DerivedFacet]) -> list[QueryFacet]:
    return [
        QueryFacet(
            id=f"{query_id}_F{existing_count + index:03d}",
            domain=item.domain,
            notion=item.notion,
            description=item.description,
            origin="derived",
            source=item.source,
        )
        for index, item in enumerate(derived, 1)
    ]


def paper_facets(context_id: str, derived: list[DerivedFacet]) -> list[Facet]:
    return [
        Facet(
            id=f"{context_id}_DF{index:03d}",
            context_id=context_id,
            domain=item.domain,
            notion=item.notion,
            description=item.description,
            origin="derived",
            source=item.source,
        )
        for index, item in enumerate(derived, 1)
    ]
