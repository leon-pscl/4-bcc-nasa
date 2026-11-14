"""C9 land-cover contract, reader and cover parameter tests.

Uses a synthetic MCD12C1-like HDF4 granule (the only way to exercise the real
reader without the 1.2 GB production files) and a synthetic cell_cover fixture
for the API-level tests, so CI does not need the NASA files either.
"""

import glob
import json
import os

import numpy as np
import pandas as pd
import pytest

from firecal.analytics.area import Area
from firecal.analytics.series import seam_series
from firecal.config import Settings
from firecal.contracts import validate_cover
from firecal.landcover.ingest import build_cell_cover, igbp_class_of

SMALL_BBOX = [112.0, -4.0, 114.0, -3.0]  # ~25k km2, inside southeast_asia

CELLS = {
    "forest": 5,     # mixed forest
    "farmland": 12,  # cropland
    "other_vegetation": 10,  # grasslands
    "other": 13,     # urban
}


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
    assert igbp_class_of(17) == "other"
    assert igbp_class_of(255) == "other"


def _region_cell(lat, lon):
    import math
    return (math.floor(lat / 0.05), math.floor(lon / 0.05))


@pytest.fixture
def hdf_granule(tmp_path):
    """A synthetic MCD12C1 v061-shaped granule in tmp_path/MCD12C1.A0001001.061.1.hdf."""
    pyhdf = pytest.importorskip("pyhdf.SD")
    from pyhdf.SD import SD, SDC
    from pyhdf.HDF import HDF
    grid_n = 3600
    path = str(tmp_path / "MCD12C1.A2019001.061.1.hdf")

    # cell positions: lat irrespective of region; pick lat inside southeast_asia bbox,
    # e.g. lat ~ +0.025 (row 1798), lon ~ 110.025 (col 2200)
    row, col = 1798, 2200

    f = SD(path, SDC.WRITE | SDC.CREATE)
    d1 = f.create("Majority_Land_Cover_Type_1", SDC.INT16, (grid_n, grid_n))
    m = np.zeros((grid_n, grid_n), dtype=np.int16)
    for (cls, dr) in ((5, (row, col)), (12, (row, col + 1)),
                      (10, (row, col + 2)), (13, (row, col + 3))):
        m[dr] = cls
    d1[:] = m
    d2 = f.create("Majority_Land_Cover_Type_1_Assessment", SDC.INT16, (grid_n, grid_n))
    a = np.full((grid_n, grid_n), 60, dtype=np.int16)
    d2[:] = a
    d3 = f.create("Land_Cover_Type_1_Percent", SDC.INT16, (17, grid_n, grid_n))
    # bands per IGBP class; class 5 cell gets 100% band 5, class 12 cell gets 60/40 split
    pct = np.zeros((17, grid_n, grid_n), dtype=np.int16)
    pct[4, row, col] = 100                # IGBP 5 = band index 4
    pct[11, row, col + 1] = 70            # IGBP 12
    pct[13, row, col + 1] = 30            # IGBP 14 (crop split)
    pct[9, row, col + 2] = 80             # IGBP 10
    pct[12, row, col + 3] = 100           # IGBP 13
    d3[:] = pct
    f.end()
    return path


def test_build_cell_cover_from_hdf4(hdf_granule, tmp_path):
    from firecal.config import Settings

    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    settings.REGIONS = {"t": (109.0, -1.0, 114.0, 1.0)}

    os.makedirs(settings.DATA_RAW + "/landcover", exist_ok=True)
    import shutil
    shutil.copy(hdf_granule, os.path.join(settings.DATA_RAW, "landcover", "MCD12C1.A2019001.061.1.hdf"))

    written = build_cell_cover(settings)
    assert written == [2019]

    import duckdb
    con = duckdb.connect()
    root = str(tmp_path / "processed" / "cell_cover" / "**" / "*.parquet")
    rows = con.execute(f"SELECT cell_lat_idx, cell_lon_idx, year, cover_class, forest_pct, crop_pct, majority_confidence "
                       f"FROM read_parquet('{root}') ORDER BY cell_lon_idx").fetchall()
    classes = {r[3]: r for r in rows}
    assert set(classes) == {"forest", "farmland", "other_vegetation", "other"}
    assert classes["forest"][4] == 100  # forest_pct
    assert classes["forest"][5] == 0    # crop_pct
    assert classes["farmland"][5] == 100  # crop_pct sums IGBP 12 + 14 bands
    assert classes["farmland"][4] == 0
    assert classes["other_vegetation"][4] == 0
    assert classes["other"][4] == 0
    df = pd.DataFrame([{"cell_lat_idx": r[0], "cell_lon_idx": r[1], "year": r[2],
                        "cover_class": r[3], "forest_pct": r[4], "crop_pct": r[5],
                        "majority_confidence": r[6]} for r in rows])
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    df["year"] = df["year"].astype("int16")
    df["forest_pct"] = df["forest_pct"].astype("int8")
    df["crop_pct"] = df["crop_pct"].astype("int8")
    df["majority_confidence"] = df["majority_confidence"].astype("int8")
    validate_cover(df)


def _smoke_settings(tmp_path):
    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    settings.REGIONS = {"test_region": (-180.0, -90.0, 180.0, 90.0)}
    settings.GRID_DEG, settings.TILE_DEG = 0.05, 1.0
    settings.CALIBRATION_YEARS = (2013, 2017)
    settings.VALIDATION_YEARS = (2018, 2021)
    settings.MIN_CALIBRATION_CELLDAYS = 30
    settings.MAX_AREA_KM2 = 500_000
    settings.SWITCH_DATE = "2012-02-01"
    return settings


def _write_xwalk(root):
    """cells: A(forest), B(farmland), C(other_vegetation), D(other) in one cell column layout."""
    coords = {"forest": (-3.975, 112.025), "farmland": (-3.975, 112.075),
              "other_vegetation": (-3.975, 112.125), "other": (-3.975, 112.175)}
    import math
    df = pd.DataFrame([
        {"cell_lat_idx": math.floor(lat / 0.05), "cell_lon_idx": math.floor(lon / 0.05),
         "year": year, "cover_class": cls,
         "forest_pct": 100 if cls == "forest" else 0,
         "crop_pct": 100 if cls == "farmland" else 0,
         "majority_confidence": 80}
        for year in range(2002, 2025) for cls, (lat, lon) in coords.items()
    ])
    cov_dir = root / "cell_cover"
    cov_dir.mkdir(parents=True, exist_ok=True)
    for year in df["year"].unique():
        sub = df[df["year"] == year]
        d_dir = cov_dir / f"year={year}"
        d_dir.mkdir(exist_ok=True)
        sub.to_parquet(d_dir / "part.parquet", index=False)


def _write_harmonized(root):
    import math
    coords = {"forest": (-3.975, 112.025), "farmland": (-3.975, 112.075),
              "other_vegetation": (-3.975, 112.125), "other": (-3.975, 112.175)}
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
            d_dir = root / "harmonized_daily" / f"region={region}" / f"year={year}"
            d_dir.mkdir(parents=True, exist_ok=True)
            sub.to_parquet(d_dir / "part.parquet", index=False)
    cd = pd.DataFrame(cd_rows, columns=["region", "cell_lat_idx", "cell_lon_idx",
                                        "tile_id", "date_local", "year", "platform",
                                        "n_detections", "frp_sum"])
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    for year in cd["year"].unique():
        for region in cd["region"].unique():
            sub = cd[(cd["year"] == year) & (cd["region"] == region)]
            d_dir = root / "celldays" / f"region={region}" / f"year={year}"
            d_dir.mkdir(parents=True, exist_ok=True)
            sub.to_parquet(d_dir / "part.parquet", index=False)


@pytest.fixture
def env(tmp_path):
    settings = _smoke_settings(tmp_path)
    processed = tmp_path / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    _write_xwalk(processed)
    _write_harmonized(processed)
    cov = [{"name": "test_region", "label": "Test", "bbox": SMALL_BBOX,
            "countries": ["T"], "start": "2003-01-01", "end": "2026-06-15",
            "platforms": ["Aqua", "SNPP"], "latest_date": "2026-06-15",
            "synthetic": False}]
    json.dump(cov, open(processed / "coverage.json", "w"))
    json.dump({"detections": "dv1", "celldays": "dv1", "harmonized_daily": "dv1",
               "cell_cover": "dv1"},
              open(processed / "data_version.json", "w"))
    return settings


def test_cover_totals_and_year_rule(env):
    import duckdb
    area = Area.from_bbox(*SMALL_BBOX)
    out_all = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="all")
    out_forest = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="forest")
    out_farm = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="farmland")
    out_other = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region", cover="other")

    # every June of the years present; forest+farmland+other must match 'all'
    def juni(out):
        return [v for i, v in enumerate(out["harmonized"]) if i and out["months"][i].endswith("-06")]

    all_sum = sum(juni(out_all))
    forest_sum = sum(juni(out_forest))
    farm_sum = sum(juni(out_farm))
    other_sum = sum(juni(out_other))
    assert all_sum == pytest.approx(forest_sum + farm_sum + other_sum)
    # default (no cover) behaves exactly like cover=all
    out_default = seam_series(area, "2019-01-01", "2026-12-31", env, region="test_region")
    assert out_default["harmonized"] == out_all["harmonized"]
    # year rule: fires in 2025 and 2026 use 2024 cover (y-1 clamped to 2024)
    june_26 = juni(out_all)
    assert june_26[-1] == pytest.approx(9.0)  # forest 3 + farmland 3 + other_veg 1.5 + other 1.5


def test_all_classes_sum_to_all(env):
    area = Area.from_bbox(*SMALL_BBOX)
    a = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region")
    f = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="forest")
    fa = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="farmland")
    o = seam_series(area, "2003-01-01", "2019-12-31", env, region="test_region", cover="other")
    assert sum(a["harmonized"]) == pytest.approx(sum(f["harmonized"]) + sum(fa["harmonized"]) + sum(o["harmonized"]))
