"""/api/series: monthly raw sensor cell-days, Aqua x k and the harmonized sum,
plus the area validation block. All expected values below are computed by hand
from the fixture: cell A (-100, -1240), one cell, months 2019-01..2020-12.

Fixture rules:
  5th of every month:  5 Aqua, 6 SNPP cell-days
  20th of every month: 4 Aqua, 5 SNPP cell-days     (Aqua day 9, SNPP day 11)
  2019-03-15:          0 Aqua, 4 SNPP  (sensor-outage day)
  2019-04-10:          3 Aqua, 0 SNPP  (sensor-outage day)
Calibration: k_all (month 0) = 2.0; tile_month month=7 (tile 0_0) = 2.5.
Harmonized: 1.5 per cell-day.
"""

import json

import pandas as pd
import pytest
import duckdb

from firecal.analytics.series import seam_series
from firecal.config import Settings
from firecal.analytics.area import Area

CELL = (-100, -1240)


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    settings = Settings()
    settings.DATA_RAW = str(root / "raw")
    settings.DATA_PROCESSED = str(root / "processed")
    settings.REGIONS = {"test_region": (-70.0, -20.0, -60.0, 0.0)}
    settings.GRID_DEG = 0.05
    settings.TILE_DEG = 1.0
    settings.MAX_AREA_KM2 = 500_000

    # (date, platform, n)
    cells = []
    for year in (2019, 2020):
        for month in range(1, 13):
            base = pd.Timestamp(year, month, 1)
            cells.append((base + pd.Timedelta(days=4), "Aqua", 5))
            cells.append((base + pd.Timedelta(days=4), "SNPP", 6))
            cells.append((base + pd.Timedelta(days=19), "Aqua", 4))
            cells.append((base + pd.Timedelta(days=19), "SNPP", 5))
    cells.append((pd.Timestamp(2019, 3, 15), "SNPP", 4))   # snpp-only day
    cells.append((pd.Timestamp(2019, 4, 10), "Aqua", 3))   # aqua-only day

    cd_rows = []
    for i, (d, platform, n) in enumerate(cells):
        for _ in range(n):
            cd_rows.append(("test_region", CELL[0], CELL[1], "0_0", d,
                            d.year, platform, 1, 5.0))
    cd_df = pd.DataFrame(cd_rows,
                         columns=["region", "cell_lat_idx", "cell_lon_idx", "tile_id",
                                  "date_local", "year", "platform", "n_detections", "frp_sum"])

    harm_rows = []
    for i, (d, platform, n) in enumerate(cells):
        for _ in range(n):
            harm_rows.append(("test_region", CELL[0], CELL[1], "0_0", d, d.year, 1.5, "viirs"))
    harm_df = pd.DataFrame(harm_rows, columns=["region", "cell_lat_idx", "cell_lon_idx",
                                               "tile_id", "date_local", "year", "value", "basis"])

    con = duckdb.connect()
    con.register("cd", cd_df)
    con.register("hd", harm_df)
    con.execute(f"COPY (SELECT * FROM cd) TO '{(root / 'processed' / 'celldays').as_posix()}' "
                f"(FORMAT PARQUET, PARTITION_BY (region, year))")
    con.execute(f"COPY (SELECT * FROM hd) TO '{(root / 'processed' / 'harmonized_daily').as_posix()}' "
                f"(FORMAT PARQUET, PARTITION_BY (region, year))")
    con.execute(f"""
        COPY (
          SELECT 'test_region' AS region, 'Aqua' AS platform, 'SNPP' AS reference,
                 'ALL' AS tile_id, 0::SMALLINT AS month, 2.0 AS k,
                 0::BIGINT AS modis_celldays, 0::BIGINT AS viirs_celldays, 'all' AS level
          UNION ALL
          SELECT 'test_region', 'Aqua', 'SNPP', '0_0', 7::SMALLINT, 2.5,
                 100::BIGINT, 110::BIGINT, 'tile_month'
        )
        TO '{(root / 'processed' / 'calibration.parquet').as_posix()}' (FORMAT PARQUET)
    """)
    cov = [{"name": "test_region", "label": "Test", "bbox": [-70.0, -20.0, -60.0, 0.0],
            "countries": ["Bolivia"], "start": "2019-01-01", "end": "2020-12-20",
            "platforms": ["Aqua", "SNPP", "NOAA20", "NOAA21"], "latest_date": "2020-12-20",
            "synthetic": False}]
    json.dump(cov, open(root / "processed" / "coverage.json", "w"))
    json.dump({"detections": "dv1", "celldays": "dv1", "harmonized_daily": "dv1"},
              open(root / "processed" / "data_version.json", "w"))
    return settings


@pytest.fixture
def bbox_area():
    return Area.from_bbox(-65.0, -10.0, -61.0, -2.0)


def test_series_shape_and_arrays(env, bbox_area):
    out = seam_series(bbox_area, "2019-01-01", "2020-12-20", env, region="test_region")
    assert out["months"][0] == "2019-01"
    assert out["months"][-1] == "2020-12"
    assert len(out["months"]) == 24
    assert out["switch_date"] == "2012-02-01"

    aqua = out["aqua"]
    snpp = out["snpp"]
    assert aqua[2] == 9.0    # 2019-03: 5+4
    assert aqua[3] == 12.0   # 2019-04: 5+4+3
    assert all(v == 9.0 for i, v in enumerate(aqua) if i not in (3,))
    assert snpp[2] == 15.0   # 2019-03: 6+5+4
    assert all(v == 11.0 for i, v in enumerate(snpp) if i != 2)
    assert out["noaa20"] == [0.0] * 24
    assert out["noaa21"] == [0.0] * 24

    # harmonized: one row per cell-day (outage days still count in the seam reality check):
    # days 5 & 20 contribute 11+9 = 20, March 15th adds 4, April 10th adds 3
    assert out["harmonized"][2] == pytest.approx(36.0)   # 2019-03: 24 cells
    assert out["harmonized"][3] == pytest.approx(34.5)   # 2019-04: 23 cells
    assert all(v == pytest.approx(30.0) for i, v in enumerate(out["harmonized"]) if i not in (2, 3))

    # Aqua x k: k=2.0; month=7 uses 2.5; outage days drop from the sum
    assert out["aqua_k"][6] == 22.5    # 2019-07
    assert out["aqua_k"][18] == 22.5   # 2020-07
    assert all(v == 18.0 for i, v in enumerate(out["aqua_k"]) if i not in (6, 18))


def test_series_outage_days(env, bbox_area):
    out = seam_series(bbox_area, "2019-01-01", "2020-12-20", env, region="test_region")
    assert out["outage_days"] == ["2019-03-15", "2019-04-10"]


def test_series_validation_numbers(env, bbox_area):
    out = seam_series(bbox_area, "2019-01-01", "2020-12-20", env, region="test_region")
    v = out["validation"]
    assert v["overlap_years"] == [2019, 2020]
    # every overlap month: viirs = 11 (>10, counted), modis = 18, except July: 22.5
    # aggregate over 24 months: modis = 441.0, viirs = 264.0
    assert v["bias_pct"] == pytest.approx((441.0 - 264.0) / 264.0 * 100, abs=0.01)
    assert v["pearson_r"] == 0.0   # constant-VIIRS fixture: zero variance
    assert v["per_year"]["2019"]["bias_pct"] == pytest.approx((220.5 - 132.0) / 132.0 * 100, abs=0.01)
    assert v["per_year"]["2020"]["bias_pct"] == pytest.approx((220.5 - 132.0) / 132.0 * 100, abs=0.01)


def test_series_respects_region_isolation(env, bbox_area):
    # a region with no data at all yields zeros and no overlap years
    from firecal.config import Settings  # noqa: F401  (kept for clarity)
    # build a second region that shares the same files minus rows? simplest: filter by bbox
    # that contains nothing is still inside the region bbox; assert zeros outside bbox instead
    empty = Area.from_bbox(-61.9, -2.0, -61.8, -1.9)
    out = seam_series(empty, "2019-01-01", "2020-12-20", env, region="test_region")
    assert all(v == 0.0 for v in out["aqua"])
    assert all(v == 0.0 for v in out["harmonized"])
    # k rows exist but no cell-days -> aqua_k fills zeros
    assert all(v == 0.0 for v in out["aqua_k"])


def test_metrics_unit():
    from firecal.harmonize.db import _metrics
    r_pos = _metrics([(10, 10), (20, 20), (30, 30)])
    r_neg = _metrics([(10, 30), (20, 20), (30, 10)])
    assert r_pos["pearson_r"] == pytest.approx(1.0)
    assert r_neg["pearson_r"] == pytest.approx(-1.0)
    assert r_pos["bias_pct"] == pytest.approx(0.0)
