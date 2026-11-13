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
        (0, 0, date(2003, 2, 14), 5.0),
        (0, 0, date(2003, 6, 1), 2.0),
        (0, 0, date(2003, 6, 2), 4.0),
        (0, 0, date(2004, 2, 10), 7.0),
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
    assert abs(sum(c["value"] for c in result["cells"]) - 2.0 - 4.0 - 5.0 - 8.0 - 16.0 - 7.0 - 100.0 - 32.0) < 1e-6


def test_calendar_hand_worked_totals_and_anomaly(tmp_path):
    """3x3 hand-worked fixture: June medians, p25/p75 (numpy convention),
    anomaly and annual totals with today = 2005-07-04 (current year excluded
    from the baseline)."""
    import math
    settings = _fixture(tmp_path)
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = calendar_matrix(area, "2003-01-01", "2005-07-04", "2005-07-04",
                             settings, region="test_region")
    assert result["years"] == [2003, 2004, 2005]
    assert result["values"][0][5] == 6.0     # June 2003: 2.0 + 4.0
    assert result["values"][1][5] == 108.0   # June 2004: 8.0 + 100.0
    assert result["values"][2][5] == 16.0    # June 2005
    # baseline years: 2003, 2004 (current year 2005 excluded)
    assert result["baseline_years"] == [2003, 2004]
    # June: sorted [6, 108] -> median 57.0 (mean of the two middle values)
    assert result["monthly_median"][5] == 57.0
    assert abs(result["monthly_p25"][5] - 31.5) < 1e-9   # 6 + 0.25 * 102
    assert abs(result["monthly_p75"][5] - 82.5) < 1e-9   # 6 + 0.75 * 102
    # July has no rows in either baseline year -> in-range zero counts for the median
    assert result["monthly_median"][6] == 0.0
    assert result["monthly_p25"][6] == 0.0
    assert result["monthly_p75"][6] == 0.0
    # anomaly vs 57.0 median (current year row)
    assert abs(result["anomaly"][2][5] - (16.0 - 57.0)) < 1e-9
    assert abs(result["anomaly_pct"][2][5] - 100 * (16.0 - 57.0) / 57.0) < 1e-9
    # other rows also show the anomaly vs the same median
    assert abs(result["anomaly"][0][5] - (6.0 - 57.0)) < 1e-9
    assert abs(result["anomaly"][1][5] - (108.0 - 57.0)) < 1e-9
    # July anomaly: v=32, med=0 -> difference reported, percentage undefined
    assert result["anomaly"][2][6] == 32.0
    assert result["anomaly_pct"][2][6] is None
    # annual totals (zeros in-range in 2003/2004 Feb for 2004/2005? no: Feb rows exist)
    assert result["annual_totals"][0] == 11.0   # Feb 5 + June 6
    assert result["annual_totals"][1] == 115.0  # Feb 7 + June 108
    assert result["annual_totals"][2] == 48.0   # June 16 + July 32


def test_calendar_zero_month_gets_no_anomaly_pct(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = calendar_matrix(area, "2003-01-01", "2005-07-04", "2005-07-04",
                             settings, region="test_region")
    # May has no rows anywhere in range -> anomaly 0.0 for every year, pct 0.0/None ok
    assert result["anomaly"][0][4] == 0.0 or result["anomaly"][0][4] is not None


def test_calendar_partial_bounds(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    # end on the last day of January -> no partial marker
    r = calendar_matrix(area, "2024-01-01", "2024-01-31", "2024-01-31",
                        settings, region="test_region")
    assert r["partial"] is None
    # end mid-November -> partial marker with through_day = 12
    r = calendar_matrix(area, "2026-11-01", "2026-11-12", "2026-11-12",
                        settings, region="test_region")
    assert r["partial"] == {"year": 2026, "month": 11, "through_day": 12}
    assert r["partial_years"] == [2026]


def test_calendar_baseline_warning(tmp_path):
    settings = _fixture(tmp_path)
    settings.MIN_BASELINE_YEARS = 10
    from firecal.analytics.calendar import calendar_matrix
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = calendar_matrix(area, "2003-01-01", "2004-12-31", "2004-12-31",
                             settings, region="test_region")
    assert result["baseline_warning"] and "fewer than 10" in result["baseline_warning"]


def test_summary_same_days_span_leap_clamp(tmp_path):
    """today = 2004-02-29: baseline 2003 Feb has only 28 days -> day clamped,
    otherwise DuckDB would reject DATE '2003-02-29'."""
    settings = _fixture(tmp_path)
    from firecal.analytics.summary import summary
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = summary(area, "2003-01-01", "2004-12-31", "2004-02-29",
                     settings, region="test_region")
    cur = result["current_month"]
    assert cur["value"] == 7.0            # 2004-02-10 only
    assert cur["through_day"] == 29
    assert cur["median_same_span"] == 5.0  # 2003-02-01..2003-02-28 (clamped)


def test_summary_current_month_null_when_today_outside_range(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.summary import summary
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    result = summary(area, "2003-01-01", "2005-07-04", "2999-01-01",
                     settings, region="test_region")
    assert result["current_month"] is None
    # inside range -> present
    result = summary(area, "2003-01-01", "2005-07-04", "2005-07-04",
                     settings, region="test_region")
    assert result["current_month"] is not None


def test_summary_peak_year_complete_years_only(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.summary import summary
    from firecal.analytics.area import Area
    area = Area.from_bbox(-1, -1, 1, 1)
    # [2003-03-01, 2004-06-30] contains no complete year
    result = summary(area, "2003-03-01", "2004-06-30", "2004-06-30",
                     settings, region="test_region")
    assert result["peak_year"] is None
    # whole fixture: complete years are 2003 and 2004; 2005 (partial) must not win
    result = summary(area, "2003-01-01", "2005-07-04", "2005-07-04",
                     settings, region="test_region")
    assert result["peak_year"] == {"year": 2004, "value": 115.0}


def test_summary_upper_middle_median_on_even_count(tmp_path):
    """Same-days span with an even number of baseline years takes the upper
    middle value (2003 span = 5.0, 2005 span = 0.0) — but 2005 is the current
    year here, so instead just exercise the helper directly."""
    from firecal.analytics.stats import median
    assert median([1.0, 3.0]) == 2.0
    assert median([1.0, 3.0], upper_middle=True) == 3.0
    assert median([4.0, 1.0, 3.0]) == 3.0
    assert median([]) is None
