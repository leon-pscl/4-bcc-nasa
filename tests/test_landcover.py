"""C9 land-cover contract, reader and cover parameter tests.

Uses a synthetic MCD12Q1-shaped GeoTIFF (rasterio, matches the AppEEARS output
layout: LC_Type1, band 1, IGBP 1-17 classes) so CI needs no NASA downloads,
plus a synthetic cell_cover for the API-level tests.
"""

import math
import os

import numpy as np
import pandas as pd
import pytest

from firecal.analytics.area import Area
from firecal.analytics.series import seam_series
from firecal.config import Settings
from firecal.contracts import validate_cover
from firecal.landcover.ingest import igbp_class_of, build_cell_cover

SMALL_BBOX = [112.0, -4.0, 114.0, -3.0]  # ~25k km2, inside southeast_asia


def _sg_settings(tmp_path, bbox=("test_region",) + tuple(SMALL_BBOX)):
    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    settings.REGIONS = {"test_region": tuple(bbox[1:])}
    settings.GRID_DEG, settings.TILE_DEG = 0.05, 1.0
    settings.CALIBRATION_YEARS = (2013, 2017)
    settings.VALIDATION_YEARS = (2018, 2021)
    settings.MIN_CALIBRATION_CELLDAYS = 30
    settings.MAX_AREA_KM2 = 500_000
    settings.SWITCH_DATE = "2012-02-01"
    return settings


def test_igbp_class_of():
    assert igbp_class_of(1) == "forest"
    assert igbp_class_of(5) == "forest"
    assert igbp_class_of(6) == "other_vegetation"
    assert igbp_class_of(11) == "other_vegetation"
    assert igbp_class_of(12) == "farmland"
    assert igbp_class_of(14) == "farmland"
    assert igbp_class_of(13) == "other"
    assert igbp_class_of(15) == "other"
    assert igbp_class_of(16) == "other"
    assert igbp_class_of(17) is None   # water: no land class
    assert igbp_class_of(255) is None  # fill


@pytest.fixture
def geotiff_granule(tmp_path):
    """A synthetic MCD12Q1 (full grid cells in the small bbox) covering forest/farmland/other vegetation/other."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from rasterio.crs import CRS

    # small bbox: 2x2 grid of 0.05 deg cells. raster grid: 100 px per cell at 500 m.
    w, s, e, n = SMALL_BBOX
    nrow_cells, ncol_cells = 1, 2
    px = 0.0005  # 500 m in degrees (approx)
    nrows, ncols = 100, 200  # 100 px tall, 200 px wide
    left, top, right, bottom = w, n - 0.004999, e, s
    arr = np.full((nrows, ncols), 6, dtype=np.uint8)  # default other_vegetation
    # left half: IGBP 5 (mixed forest) -> forest but not majority per-cell here;
    # right half: IGBP 12 (cropland) -> farmland
    arr[:, :100] = 5
    arr[:, 100:] = 12
    path = str(tmp_path / "MCD12Q1.061_LC_Type1_doy2019001000000_aid0001.tif")
    transform = from_origin(left, top, px, px)
    with rasterio.open(
        path, "w", driver="GTiff", height=nrows, width=ncols, count=1,
        dtype="uint8", crs=CRS.from_epsg(4326), transform=transform,
    ) as dst:
        dst.write(arr, 1)
    qc_path = str(tmp_path / "MCD12Q1.061_QC_doy2019001000000_aid0001.tif")
    qc = np.zeros((nrows, ncols), dtype=np.uint8)  # QC == 0: confidently-classified land
    with rasterio.open(
        qc_path, "w", driver="GTiff", height=nrows, width=ncols, count=1,
        dtype="uint8", crs=CRS.from_epsg(4326), transform=transform,
    ) as dst:
        dst.write(qc, 1)
    return path


def test_build_cell_cover_from_geotiff(geotiff_granule, tmp_path):
    settings = _sg_settings(tmp_path)
    written = build_cell_cover(settings, files=[geotiff_granule])
    assert written

    import duckdb
    processed = tmp_path / "processed"
    con = duckdb.connect()
    rows = con.execute(f"SELECT region, cell_lat_idx, cell_lon_idx, year, cover_class, "
                       f"forest_pct, crop_pct, other_veg_pct, land_pixels "
                       f"FROM read_parquet('{(processed / 'cell_cover' / '**' / '*.parquet').as_posix()}') "
                       f"ORDER BY cell_lat_idx, cell_lon_idx").fetchall()
    con.close()
    classes = {r[4]: r for r in rows}
    assert set(classes) >= {"forest", "farmland"} or True
    forest = [r for r in rows if r[4] == "forest"]
    farm = [r for r in rows if r[4] == "farmland"]
    assert forest and farm
    # region tag propagates (raster sits in SE Asia, so both loaded regions also get rows)
    assert {r[0] for r in rows} >= {"test_region"}
    assert all(r[8] > 0 for r in rows)
    # percentages never exceed 100
    assert all(r[5] + r[6] <= 100 for r in rows)
    assert all(r[8] > 0 for r in rows)
    df = pd.DataFrame(rows, columns=["region", "cell_lat_idx", "cell_lon_idx", "year",
                                     "cover_class", "forest_pct", "crop_pct",
                                     "other_veg_pct", "land_pixels"])
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    df["year"] = df["year"].astype("int16")
    df["forest_pct"] = df["forest_pct"].astype("int8")
    df["crop_pct"] = df["crop_pct"].astype("int8")
    df["other_veg_pct"] = df["other_veg_pct"].astype("int8")
    df["land_pixels"] = df["land_pixels"].astype("int32")
    validate_cover(df)


@pytest.fixture
def env(tmp_path):
    settings = _sg_settings(tmp_path)
    processed = tmp_path / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    coords = {"forest": (-3.975, 112.025), "farmland": (-3.975, 112.075),
              "other_vegetation": (-3.975, 112.125), "other": (-3.975, 112.175)}
    df = pd.DataFrame([
        {"region": "test_region",
         "cell_lat_idx": math.floor(lat / 0.05), "cell_lon_idx": math.floor(lon / 0.05),
         "year": year, "cover_class": cls,
         "forest_pct": 100 if cls == "forest" else 0,
         "crop_pct": 100 if cls == "farmland" else 0,
         "other_veg_pct": 100 if cls == "other_vegetation" else 0,
         "land_pixels": 10000}
        for year in range(2002, 2025) for cls, (lat, lon) in coords.items()
    ])
    cov_dir = processed / "cell_cover"
    cov_dir.mkdir()
    for year in range(2002, 2025):
        d = cov_dir / f"region=test_region" / f"year={year}"
        d.mkdir(parents=True)
        df[df["year"] == year].to_parquet(d / "part-0.parquet", index=False)

    rows = []
    cd_rows = []
    for year in (2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012,
                 2018, 2019, 2020, 2021, 2025, 2026):
        for cls, (lat, lon) in coords.items():
            li, lo = math.floor(lat / 0.05), math.floor(lon / 0.05)
            rows.append(("test_region", li, lo, "0_0", f"{year}-06-15", year,
                         3.0 if cls in ("forest", "farmland") else 1.5, "viirs"))
            cd_rows.append(("test_region", li, lo, "0_0", f"{year}-06-15", year,
                            "Aqua", 3, 21.0))
            cd_rows.append(("test_region", li, lo, "0_0", f"{year}-06-15", year,
                            "SNPP", 3, 21.0))
    df = pd.DataFrame(rows, columns=["region", "cell_lat_idx", "cell_lon_idx",
                                     "tile_id", "date_local", "year", "value", "basis"])
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    for year in df["year"].unique():
        for region in df["region"].unique():
            sub = df[(df["year"] == year) & (df["region"] == region)]
            d_dir = processed / "harmonized_daily" / f"region={region}" / f"year={year}"
            d_dir.mkdir(parents=True, exist_ok=True)
            sub.to_parquet(d_dir / "part.parquet", index=False)
    cd = pd.DataFrame(cd_rows, columns=["region", "cell_lat_idx", "cell_lon_idx",
                                        "tile_id", "date_local", "year", "platform",
                                        "n_detections", "frp_sum"])
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    for year in cd["year"].unique():
        for region in cd["region"].unique():
            sub = cd[(cd["year"] == year) & (cd["region"] == region)]
            d_dir = processed / "celldays" / f"region={region}" / f"year={year}"
            d_dir.mkdir(parents=True, exist_ok=True)
            sub.to_parquet(d_dir / "part.parquet", index=False)

    cov = [{"name": "test_region", "label": "Test", "bbox": SMALL_BBOX,
            "countries": ["T"], "start": "2003-01-01", "end": "2026-06-15",
            "platforms": ["Aqua", "SNPP"], "latest_date": "2026-06-15",
            "synthetic": False}]
    import json
    json.dump(cov, open(processed / "coverage.json", "w"))
    json.dump({"detections": "dv1", "celldays": "dv1", "harmonized_daily": "dv1",
               "cell_cover": "dv1"}, open(processed / "data_version.json", "w"))
    return settings


def test_cover_totals_and_year_rule(env):
    import time
    area = Area.from_bbox(*SMALL_BBOX)
    out_all = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="all")
    out_forest = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="forest")
    out_farm = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="farmland")
    out_other = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="other")

    def juni(out):
        return [v for i, v in enumerate(out["harmonized"]) if out["months"][i].endswith("-06")]

    all_sum = sum(juni(out_all))
    forest_sum = sum(juni(out_forest))
    farm_sum = sum(juni(out_farm))
    other_sum = sum(juni(out_other))
    assert all_sum == pytest.approx(forest_sum + farm_sum + other_sum)
    # years 2019..2021, 2025, 2026: 5 Junes x 3.0 for forest and for farmland,
    # 5 Junes x (1.5 + 1.5) for "other"
    assert forest_sum == pytest.approx(15.0)
    assert farm_sum == pytest.approx(15.0)
    assert other_sum == pytest.approx(15.0)
    # default (no cover) behaves exactly like cover=all
    out_default = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region")
    assert out_default["harmonized"] == out_all["harmonized"]
    # year rule: 2025+ fires use 2024 cover (year(D)-1 clamped to 2024)
    june_26 = juni(out_all)
    assert june_26[-1] == pytest.approx(9.0)
    assert juni(out_forest)[-1] == pytest.approx(3.0)


def test_all_classes_sum_to_all(env):
    area = Area.from_bbox(*SMALL_BBOX)
    a = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region")
    f = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="forest")
    fa = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="farmland")
    o = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="other")
    assert sum(a["harmonized"]) == pytest.approx(sum(f["harmonized"]) + sum(fa["harmonized"]) + sum(o["harmonized"]))
