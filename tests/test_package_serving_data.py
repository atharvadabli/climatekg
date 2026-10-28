import hashlib
import json
from zipfile import ZipFile

import pytest

from scripts.package_serving_data import package


def test_package_serving_data_preserves_mount_layout(tmp_path):
    data = tmp_path / "source_data"
    assets = tmp_path / "source_assets"
    for name in ("parquet_graph", "baselines/graphrag", "baselines/plain_rag/index"):
        (data / name).mkdir(parents=True)
    (data / "parquet_graph/manifest.json").write_text(
        json.dumps({"format": "climatekg-parquet-graph"}), encoding="utf-8"
    )
    (data / "parquet_graph/claims.parquet").write_bytes(b"claims")
    (data / "baselines/graphrag/index.parquet").write_bytes(b"graph")
    (data / "baselines/plain_rag/index/data.json").write_bytes(b"plain")
    assets.mkdir()
    (assets / "watershed_pan_india_simplified.geojson").write_bytes(b"{}")
    (assets / "Global_1986-2010_KG_5m.kmz.zip").write_bytes(b"zip")

    output = tmp_path / "serving.zip"
    package(data, assets, output)

    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read("data/parquet_graph/claims.parquet") == b"claims"
        assert archive.read("assets/watershed_pan_india_simplified.geojson") == b"{}"
    assert output.with_suffix(".zip.sha256").read_text().startswith(
        hashlib.sha256(output.read_bytes()).hexdigest()
    )


def test_package_serving_data_rejects_missing_assets(tmp_path):
    with pytest.raises(ValueError, match="missing serving artifacts"):
        package(tmp_path, tmp_path, tmp_path / "serving.zip")
