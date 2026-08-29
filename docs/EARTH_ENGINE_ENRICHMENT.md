# Earth Engine Enrichment

## Scope

ClimateKG uses Google Earth Engine as the only raster enrichment backend. It
does not fall back to files on the local machine. The pan-India watershed
GeoJSON is used only as an application registry that resolves a stable
watershed ID to an exact polygon.

The same `derive_facets` function is called during paper indexing and query
processing. Every emitted Facet records the dataset, version, temporal window,
geometry hash, method, and algorithm version.

## Configuration

Install the project and authenticate Earth Engine:

```powershell
.\.venv-climatekg\Scripts\python.exe -m pip install -e .
.\.venv-climatekg\Scripts\earthengine.exe authenticate
```

Create the ignored `.env` file:

```text
EARTH_ENGINE_PROJECT=your-earth-engine-enabled-google-cloud-project
CLIMATEKG_WATERSHED_REGISTRY=E:/path/to/watershed_pan_india_simplified.geojson
```

OAuth credentials remain in Earth Engine's credential store. Do not put a
refresh token, service-account key, or key JSON content in `.env`.

## Dataset Contract

| Family | Earth Engine dataset | Period/version | Output |
|---|---|---|---|
| Aridity | `IDAHO_EPSCOR/TERRACLIMATE` | 1991-2020 | annual P, annual PET, P/PET, aridity class |
| Wind | `ECMWF/ERA5_LAND/MONTHLY_AGGR` | 1991-2020 | seasonal mean speed, wind-from direction, directional persistence |
| Terrain | `USGS/SRTMGL1_003` | SRTM V3 | elevation p10/median/p90, relief, median slope |
| Land cover | `ESA/WorldCover/v200` | 2021 v200 | pixel-area class fractions |

Dataset documentation:

- https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE
- https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR
- https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003
- https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200

## Resolution Precedence Implemented

```text
explicit GeoJSON Point/Polygon/MultiPolygon
-> explicit labeled latitude/longitude
-> exact pan-India watershed ID such as C07BRA20
-> unresolved
```

Named-place gazetteer resolution is not implemented. An unresolved place stays
`geometry=null` and receives a visible skip warning.

## Direct Smoke Test

By watershed ID:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli enrich-area `
  --watershed-id C07BRA20 `
  --output climatekg/runtime/outputs/enrichment/C07BRA20.json
```

By a GeoJSON Geometry or one-feature GeoJSON file:

```powershell
.\.venv-climatekg\Scripts\python.exe -m climatekg.cli enrich-area `
  --geometry planning_area.geojson `
  --name "planning area" `
  --output climatekg/runtime/outputs/enrichment/planning_area.json
```

The output preserves the resolved geometry, raw dataset statistics, rendered
Facets, provenance, coverage, and warnings.

## Explicit Boundaries

- No Köppen-Geiger dataset is configured in Earth Engine. The run records
  `ENRICHMENT_CLIMATE_REGIME_NOT_CONFIGURED` and emits no climate-regime Facet.
- WorldCover class fractions are implemented. Connected-component sizes and
  edge density are not yet implemented, so the run records
  `ENRICHMENT_LAND_COVER_CONFIGURATION_METRICS_NOT_IMPLEMENTED` and emits no
  patch/configuration conclusion.
- ERA5-Land provides 10 m wind, not 850 hPa wind. Provenance and descriptions
  state the actual height; the system does not silently describe it as
  pressure-level flow.
- A directionally variable seasonal wind produces no fixed-direction statement.
- Earth Engine initialization or computation failure is recorded explicitly.
  A resolved-location query stops instead of continuing without enrichment;
  indexing records the optional-stage failure as required by the indexing
  specification. No local raster is substituted.
