"""Stage 4 tests: calendar, summary, map, export over a hand-made fixture."""

import os
import shutil
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from firecal.config import Settings


def _fixture(tmp_path):
    """3 cells x 3 years, known values."""
    root = tmp_path / "data"
    os.makedirs(root / "processed" / "harmonized_daily", exist_ok=True)
    rows = [
        # (lat_idx, lon_idx, date, value)
        (0, 0, date(2003, 6, 1), 2.0),
        (0, 0, date(2003, 6, 2), 4.0),
        (0, 0, date(2004, 6, 1), 8.0),
        (0, 0, date(2005, 6, 1), 16.0),
        (1, 1, date(2004, 6, 3), 100.0),
        (0, 0, date(2005, 7, 4), 32.0),
    ]
    df = pd.DataFrame(rows, columns=["cell_lat_idx", "cell_lon_idx", "date_local", "value"])
    df["tile_id"] = "0_0"
    df["basis"] = "viirs"
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df["region"] = "test_region"
    con = duckdb.connect()
    p = str(root / "processed" / "harmonized_daily").replace(os.sep, "/")
    # partition by region/year
    con.execute(f"""
        COPY (
          SELECT region, cell_lat_idx, cell_lon_idx, '0_0' AS tile_id,
                 CAST(date_local AS DATE) AS date_local, year, value, basis
          FROM df
        ) TO '{p}' (FORMAT PARQUET, PARTITION_BY (region, year))
    """)
    coverage = [{"name": "test_region", "label": "Test Region", "bbox": [-180, -90, 180, 90],
                 "countries": ["Test"], "start": "2003-01-01", "end": "2005-07-04",
                 "platforms": ["Aqua", "SNPP"], "latest_date": "2005-07-04",
                 "synthetic": False}]
    import json
    json.dump(coverage, open(root / "processed" / "coverage.json", "w"))
    settings = Settings()
    settings.DATA_PROCESSED = str(root / "processed")
    settings.MAX_AREA_KM2 = 500_000
    settings.GRID_DEG = 0.05
    settings.MIN_BASELINE_YEARS = 1
    settings.TILE_DEG = 1.0
    return settings


def test_calendar_partial_and_values(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = calendar_matrix(area, "2003-01-01", "2004-12-31", "2004-12-31",
                             settings, region="test_region")
    assert result["years"] == [2003, 2004]
    # June 2003: cell 0,0 only: 2+4 = 6.0; June 2004: 8.0 (other cell also viirs 2004-06-03 = 100)
    assert result["values"][0][5] == 6.0
    assert result["values"][1][5] == 108.0
    assert result["partial"] is None  # end on Dec 31


def test_calendar_partial_month_marker(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = calendar_matrix(area, "2005-01-01", "2005-06-15", "2005-06-15",
                             settings, region="test_region")
    assert result["partial"] == {"year": 2005, "month": 6, "through_day": 15}
    assert result["partial_years"] == [2005]


def test_summary_latest_data_date(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.summary import summary
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = summary(area, "2003-01-01", "2005-07-04", "2005-07-04",
                     settings, region="test_region")
    assert result["total"] > 0
    assert result["latest_data_date"] == "2005-07-04"


def test_map_cells(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.maps import map_cells
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = map_cells(area, "2003-01-01", "2005-07-04", settings, region="test_region")
    assert result["grid_deg"] == 0.05
    assert len(result["cells"]) >= 1
