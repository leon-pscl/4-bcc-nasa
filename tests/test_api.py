"""Stage 5 tests: every C6 endpoint against a tiny synthetic dataset."""

import json
import os
import shutil
from datetime import date

import duckdb
import pandas as pd
import pytest

from firecal.config import Settings
from firecal.web import create_app


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "data"
    os.makedirs(root / "raw")
    os.makedirs(root / "processed")
    settings = Settings()
    settings.DATA_RAW = str(root / "raw")
    settings.DATA_PROCESSED = str(root / "processed")
    settings.REGIONS = {"test_region": (-70.0, -20.0, -60.0, 0.0)}

    # detections: a few rows across years, in test_region
    rows = []
    for i in range(30):
        year = 2020 + (i % 3)
        month = 1 + (i % 12)
        rows.append((float(i), -62.0 - i % 3, -5.0 - i % 3, date(year, month, 15),
                     "Aqua", "nominal", "D", "SP", 10.0, 1.0, 1.0, 1.0))
    for r in rows:
        pass
    months = [("2003-01-01", 2003), ("2012-03-15", 2012), ("2018-07-20", 2018), ("2026-09-10", 2026)]
    con = duckdb.connect()
    for d, y in months:
        con.execute(f"""
            COPY (SELECT 'test_region' AS region, 0 AS cell_lat_idx, 0 AS cell_lon_idx, '0_0' AS tile_id,
                    DATE '{d}' AS date_local, {y} AS year, 'Aqua' AS platform,
                    1 AS n_detections, 2.0 AS frp_sum)
            TO '{(root / 'processed' / 'celldays').as_posix()}' (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
        """)
    for d, y in months:
        con.execute(f"""
            COPY (SELECT 'test_region' AS region, 0 AS cell_lat_idx, 0 AS cell_lon_idx, '0_0' AS tile_id,
                    DATE '{d}' AS date_local, {y} AS year, 1.0 AS value, 'viirs' AS basis)
            TO '{(root / 'processed' / 'harmonized_daily').as_posix()}' (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
        """)
    con.execute(f"""
        COPY (SELECT 'test_region' AS region, 'uid1' AS uid, DATE '2018-07-20' AS date_local, TIMESTAMP '2018-07-20 00:00:00' AS acq_datetime_utc,
                     -62.0 AS latitude, -5.0 AS longitude, 'nominal' AS confidence_class, 10.0 AS frp,
                     'D' AS daynight, 'MODIS' AS sensor, 'Aqua' AS platform, 'NRT' AS processing)
        TO '{(root / 'processed' / 'detections').as_posix()}' (FORMAT PARQUET, PARTITION_BY (region), OVERWRITE_OR_IGNORE)
    """)
    cov = [{"name": "test_region", "label": "Test Region", "bbox": [-70.0, -20.0, -60.0, 0.0],
            "countries": ["Bolivia"], "start": "2003-01-01", "end": "2026-09-10",
            "platforms": ["Aqua", "SNPP"], "latest_date": "2026-09-10", "synthetic": False}]
    json.dump(cov, open(root / "processed" / "coverage.json", "w"))
    # calibration (single-file parquet)
    con.execute(f"""
        COPY (SELECT 'test_region' AS region, 'Aqua' AS platform, 'SNPP' AS reference,
                     '0_0' AS tile_id, 1::SMALLINT AS month, 2.5::DOUBLE AS k,
                     10::BIGINT AS modis_celldays, 25::BIGINT AS viirs_celldays,
                     'tile_month' AS level)
        TO '{(root / "processed" / "calibration.parquet").as_posix()}' (FORMAT PARQUET)
    """)
    validation = {
        "calibration_years": {"years": [2013], "metrics": {"pearson_r": 0.99, "bias_pct": 1.0,
                                                            "median_abs_pct_error": 2.0,
                                                            "monthly_viirs": [1.0] * 12,
                                                            "monthly_modis": [1.0] * 12},
                              "per_year": {}},
        "validation_years": {"years": [2018], "metrics": {"pearson_r": 0.99, "bias_pct": 2.0,
                                                           "median_abs_pct_error": 3.0,
                                                           "monthly_viirs": [1.0] * 12,
                                                           "monthly_modis": [1.0] * 12},
                             "per_year": {}},
    }
    json.dump(validation, open(root / "processed" / "validation.json", "w"))
    dv = "testdv123"
    json.dump({"detections": dv, "celldays": dv, "harmonized_daily": dv},
              open(root / "processed" / "data_version.json", "w"))
    settings.GRID_DEG = 0.05
    settings.TILE_DEG = 1.0
    settings.MAX_AREA_KM2 = 500_000
    settings.MIN_BASELINE_YEARS = 5
    settings.MAX_MAP_CELLS = 20_000
    return settings


@pytest.fixture
def client(env):
    app = create_app(env)
    app.testing = True
    return app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] in ("ok", "stale")
    assert d["data_version"] == "testdv123"
    assert d["regions"][0]["name"] == "test_region"
    assert d["regions"][0]["age_days"] is not None


def test_calendar(client, env):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2012-01-01&end=2018-12-31")
    assert r.status_code == 200
    d = r.get_json()
    assert d["unit"] == "Hotspots (harmonized)"
    assert d["query"]["bbox"] == [-65.0, -10.0, -61.0, -2.0]
    assert d["years"] == [2012, 2013, 2014, 2015, 2016, 2017, 2018]
    assert d["data_version"] == "testdv123"
    assert r.headers["ETag"] == '"testdv123"'


def test_calendar_304(client):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2012-01-01&end=2018-12-31",
                   headers={"If-None-Match": '"testdv123"'})
    assert r.status_code == 304


def test_summary(client):
    r = client.get("/api/summary?bbox=-65,-10,-61,-2&start=2003-01-01&end=2026-09-10")
    assert r.status_code == 200
    d = r.get_json()
    assert d["latest_data_date"] == "2026-09-10"
    assert d["synthetic"] is False


def test_map(client):
    r = client.get("/api/map?bbox=-65,-10,-61,-2&start=2012-01-01&end=2018-12-31")
    assert r.status_code == 200
    d = r.get_json()
    assert d["grid_deg"] == 0.05
    assert "cells" in d


def test_hotspots(client):
    r = client.get("/api/hotspots?bbox=-65,-10,-61,-2&start=2003-01-01&end=2026-09-10&page=1&page_size=10")
    assert r.status_code == 200
    d = r.get_json()
    assert "rows" in d
    assert d["page_size"] == 10


def test_coverage(client):
    r = client.get("/api/coverage")
    assert r.status_code == 200
    d = r.get_json()
    assert d["regions"][0]["name"] == "test_region"
    assert d["regions"][0]["label"] == "Test Region"
    assert d["regions"][0]["countries"] == ["Bolivia"]
    assert d["starter_areas"] == []  # no starter areas for test_region in regions.json


def test_methods(client):
    r = client.get("/api/methods?region=test_region")
    assert r.status_code == 200
    d = r.get_json()
    assert d["calibration"]["k_median"] == 2.5
    assert d["calibration"]["k_min"] == 2.5
    assert d["calibration"]["k_max"] == 2.5
    assert d["calibration"]["count_per_level"] == {"tile_month": 1}
    assert d["validation"]["calibration_years"]["years"] == [2013]


def test_400_invalid_dates(client):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=not-a-date&end=2018-12-31")
    assert r.status_code == 400
    d = r.get_json()
    assert d["field"] == "start"


def test_400_end_after_latest(client):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2003-01-01&end=2030-01-01")
    assert r.status_code == 400
    d = r.get_json()
    assert d["field"] == "end"


def test_422_outside_coverage(client):
    r = client.get("/api/calendar?bbox=95,-45,99,-42&start=2003-01-01&end=2018-12-31")
    assert r.status_code == 422


def test_400_bbox_too_large(client):
    r = client.get("/api/calendar?bbox=-180,-90,180,90&start=2012-01-01&end=2018-12-31")
    assert r.status_code == 400
