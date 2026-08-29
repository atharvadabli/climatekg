from __future__ import annotations

from typing import Any


class EarthEngineConfigurationError(RuntimeError):
    pass


class EarthEngineBackend:
    """Synchronous Earth Engine adapter used by both indexing and querying."""

    def __init__(self, project: str | None, datasets: dict[str, dict[str, Any]], period: dict[str, str]) -> None:
        if not project:
            raise EarthEngineConfigurationError(
                "EARTH_ENGINE_PROJECT is required for enrichment; add it to .env or the process environment"
            )
        import ee

        try:
            ee.Initialize(project=project)
        except Exception as exc:
            raise EarthEngineConfigurationError(f"Earth Engine initialization failed for project {project}: {exc}") from exc
        self.ee = ee
        self.datasets = datasets
        self.period = period

    def _geometry(self, geometry: dict[str, Any]) -> Any:
        return self.ee.Geometry(geometry)

    def _reduce(self, image: Any, reducer: Any, geometry: Any, scale: float) -> dict[str, Any]:
        result = image.reduceRegion(
            reducer=reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=10_000_000_000,
            tileScale=4,
        ).getInfo()
        return result or {}

    def _coverage(self, image: Any, geometry: Any, scale: float, geometry_type: str) -> float:
        if geometry_type == "Point":
            values = self._reduce(image.mask(), self.ee.Reducer.first(), geometry, scale)
            return 1.0 if any(value is not None and value != 0 for value in values.values()) else 0.0
        valid_area = self._reduce(
            self.ee.Image.pixelArea().updateMask(image.mask().reduce(self.ee.Reducer.min())),
            self.ee.Reducer.sum(),
            geometry,
            scale,
        ).get("area")
        total_area = geometry.area(maxError=1).getInfo()
        return min(1.0, float(valid_area or 0.0) / max(float(total_area or 0.0), 1.0))

    def _area_weighted_mean(self, image: Any, band: str, geometry: Any, scale: float, geometry_type: str) -> float | None:
        selected = image.select(band)
        if geometry_type == "Point":
            value = self._reduce(selected, self.ee.Reducer.first(), geometry, scale).get(band)
            return None if value is None else float(value)
        area = self.ee.Image.pixelArea().updateMask(selected.mask())
        numerator = self._reduce(selected.multiply(area), self.ee.Reducer.sum(), geometry, scale).get(band)
        denominator = self._reduce(area, self.ee.Reducer.sum(), geometry, scale).get("area")
        if numerator is None or not denominator:
            return None
        return float(numerator) / float(denominator)

    def aridity(self, geometry: dict[str, Any]) -> dict[str, Any]:
        config = self.datasets["aridity"]
        target = self._geometry(geometry)
        collection = self.ee.ImageCollection(config["id"]).filterDate(self.period["start"], self.period["end"])
        years = int(self.period["end"][:4]) - int(self.period["start"][:4])
        precipitation = collection.select("pr").sum().divide(years).rename("precipitation_mm")
        pet = collection.select("pet").sum().multiply(0.1).divide(years).rename("pet_mm")
        image = precipitation.addBands(pet)
        scale = config["scale_m"]
        return {
            "coverage": self._coverage(image, target, scale, geometry["type"]),
            "precipitation_mm": self._area_weighted_mean(image, "precipitation_mm", target, scale, geometry["type"]),
            "pet_mm": self._area_weighted_mean(image, "pet_mm", target, scale, geometry["type"]),
        }

    def wind(self, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        config = self.datasets["wind"]
        target = self._geometry(geometry)
        scale = config["scale_m"]
        collection = (
            self.ee.ImageCollection(config["id"])
            .filterDate(self.period["start"], self.period["end"])
            .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
        )

        def summarize(item: Any) -> Any:
            image = self.ee.Image(item)
            values = image.reduceRegion(
                reducer=self.ee.Reducer.mean(),
                geometry=target,
                scale=scale,
                maxPixels=10_000_000_000,
                tileScale=4,
            )
            return self.ee.Dictionary(values).set("month", image.date().get("month")).set("date", image.date().format("YYYY-MM"))

        summaries = collection.toList(collection.size()).map(summarize).getInfo()
        records = []
        for properties in summaries:
            u = properties.get("u_component_of_wind_10m")
            v = properties.get("v_component_of_wind_10m")
            if u is not None and v is not None:
                records.append({"date": properties.get("date"), "month": int(properties["month"]), "u": float(u), "v": float(v)})
        return records

    def terrain(self, geometry: dict[str, Any]) -> dict[str, Any]:
        config = self.datasets["terrain"]
        target = self._geometry(geometry)
        elevation = self.ee.Image(config["id"]).select("elevation")
        slope = self.ee.Terrain.slope(elevation).rename("slope")
        image = elevation.addBands(slope)
        scale = config["scale_m"]
        stats = self._reduce(image, self.ee.Reducer.percentile([10, 50, 90]), target, scale)
        return {
            "coverage": self._coverage(image, target, scale, geometry["type"]),
            "elevation_p10_m": stats.get("elevation_p10"),
            "elevation_median_m": stats.get("elevation_p50"),
            "elevation_p90_m": stats.get("elevation_p90"),
            "slope_median_deg": stats.get("slope_p50"),
        }

    def land_cover(self, geometry: dict[str, Any]) -> dict[str, Any]:
        config = self.datasets["land_cover"]
        target = self._geometry(geometry)
        image = self.ee.ImageCollection(config["id"]).first().select("Map").rename("class")
        scale = config["scale_m"]
        if geometry["type"] == "Point":
            value = self._reduce(image, self.ee.Reducer.first(), target, scale).get("class")
            fractions = {} if value is None else {str(int(value)): 1.0}
            return {"coverage": 1.0 if fractions else 0.0, "fractions": fractions}
        grouped = self._reduce(
            self.ee.Image.pixelArea().rename("area").addBands(image),
            self.ee.Reducer.sum().group(groupField=1, groupName="class"),
            target,
            scale,
        ).get("groups", [])
        areas = {str(int(item["class"])): float(item["sum"]) for item in grouped}
        valid_area = sum(areas.values())
        total_area = float(target.area(maxError=1).getInfo())
        fractions = {key: value / valid_area for key, value in areas.items()} if valid_area else {}
        return {"coverage": min(1.0, valid_area / max(total_area, 1.0)), "fractions": fractions}
