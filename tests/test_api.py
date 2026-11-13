"""Stage 5 tests: every C6 endpoint against a tiny synthetic dataset."""

import json
import os
from datetime import date

import duckdb
import pandas as pd
import pytest

from firecal.config import Settings
from firecal.web import create_app

# fixture values (cell A, one row per date)
JUNE = {2017: 2, 2018: 3, 2019: 4, 2020: 5, 2021: 6, 2022: 7,
        2023: 8, 2024: 9, 2025: 10, 2026: 11}
SEPT = {y: y - 2014 for y in range(2017, 2027)}


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "data"
    os.makedirs(root / "raw")
    os.makedirs(root / "processed")
    settings = Settings()
    settings.DATA_RAW = str(root / "raw")
    settings.DATA_PROCESSED = str(root / "processed")
    settings.REGIONS = {"test_region": (-70.0, -20.0, -60.0, 0.0)}

    CELL = (-100, -1240)   # center (-4.975, -61.975), inside bbox -65,-10,-61,-2; (cell_lat_idx, cell_lon_idx)
    rows = []
    for y, v in JUNE.items():
        rows.append((CELL[0], CELL[1], pd.Timestamp(y, 6, 15), float(v)))
    for y, v in SEPT.items():
        rows.append((CELL[0], CELL[1], pd.Timestamp(y, 9, 7), float(v)))
    rows.append((CELL[0], CELL[1], pd.Timestamp(2026, 9, 21), 4.0))
    df = pd.DataFrame(rows, columns=["cell_lat_idx", "cell_lon_idx", "date_local", "value"])
    df["tile_id"] = "0_0"
    df["basis"] = "viirs"
    df["year"] = df.date_local.dt.year
    df["region"] = "test_region"

    con = duckdb.connect()
    harm = (root / "processed" / "harmonized_daily").as_posix()
    cell = (root / "processed" / "celldays").as_posix()
    det = (root / "processed" / "detections").as_posix()
    con.register("df", df)
    con.execute(f"""
        COPY (SELECT region, cell_lat_idx, cell_lon_idx, tile_id,
                     CAST(date_local AS DATE) AS date_local, year, value, basis
              FROM df)
        TO '{harm}' (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)
    con.execute(f"""
        COPY (SELECT region, cell_lat_idx, cell_lon_idx, tile_id,
                     CAST(date_local AS DATE) AS date_local, year, platform,
                     1 AS n_detections, 2.0 AS frp_sum
              FROM (
                SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local, year,
                       'Aqua' AS platform FROM df
                UNION ALL
                SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local, year,
                       'SNPP' AS platform FROM df
              ))
        TO '{cell}' (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)
    con.execute(f"""
        COPY (SELECT 'test_region' AS region,
                     'uid' || ROW_NUMBER() OVER () AS uid,
                     CAST(d.date_local AS DATE) AS date_local, CAST(d.date_local AS TIMESTAMP) AS acq_datetime_utc,
                     -4.975 AS latitude, -61.975 AS longitude, 'nominal' AS confidence_class,
                     10.0 AS frp, 'D' AS daynight,
                     CASE WHEN p.platform = 'Aqua' THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
                     p.platform AS platform, 'NRT' AS processing,
                     d.year AS year
              FROM df AS d CROSS JOIN (SELECT 'Aqua' AS platform UNION ALL SELECT 'SNPP') AS p)
        TO '{det}' (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)

    coverage = [{"name": "test_region", "label": "Test Region", "bbox": [-70.0, -20.0, -60.0, 0.0],
                 "countries": ["Bolivia"], "start": "2017-01-01", "end": "2026-09-21",
                 "platforms": ["Aqua", "SNPP"], "latest_date": "2026-09-21",
                 "synthetic": False}]
    json.dump(coverage, open(root / "processed" / "coverage.json", "w"))
    validation = {
        "calibration_years": {"years": [2013, 2017],
                             "metrics": {"pearson_r": 0.95, "bias_pct": 2.0,
                                         "median_abs_pct_error": 8.0,
                                         "monthly_viirs": [1] * 12,
                                         "monthly_modis": [1] * 12}},
        "validation_years": {"years": [2018, 2021],
                             "metrics": {"pearson_r": 0.9, "bias_pct": 5.0,
                                         "median_abs_pct_error": 10.0,
                                         "monthly_viirs": [1] * 12,
                                         "monthly_modis": [1] * 12}},
    }
    json.dump(validation, open(root / "processed" / "validation.json", "w"))
    con.execute(f"""
        COPY (SELECT 'test_region' AS region, 'Aqua' AS platform, 'SNPP' AS reference,
                     '0_0' AS tile_id, 7::SMALLINT AS month, 2.5::DOUBLE AS k,
                     10::BIGINT AS modis_celldays, 25::BIGINT AS viirs_celldays,
                     'tile_month' AS level)
        TO '{(root / "processed" / "calibration.parquet").as_posix()}' (FORMAT PARQUET)
    """)
    json.dump({"detections": "dv1", "celldays": "dv1", "harmonized_daily": "dv1"},
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
    assert d["data_version"] == "dv1"
    assert d["regions"][0]["name"] == "test_region"
    assert d["regions"][0]["age_days"] is not None


def test_calendar_values_and_shape(client):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21")
    assert r.status_code == 200
    d = r.get_json()
    assert d["query"]["bbox"] == [-65.0, -10.0, -61.0, -2.0]
    assert d["years"] == [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    June = {y: d["values"][i][5] for i, y in enumerate(d["years"])}
    assert June == JUNE
    assert d["partial"] == {"year": 2026, "month": 9, "through_day": 21}
    assert d["annual_totals"][-1] == JUNE[2026] + SEPT[2026] + 4.0
    assert d["synthetic"] is False


def test_summary_total_and_current_month(client):
    r = client.get("/api/summary?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21")
    assert r.status_code == 200
    d = r.get_json()
    assert d["total"] == float(sum(JUNE.values()) + sum(SEPT.values()) + 4.0)
    cur = d["current_month"]
    assert cur["through_day"] == 21
    assert cur["value"] == float(SEPT[2026] + 4.0)
    assert cur["median_same_span"] == float(sorted(SEPT[y] for y in range(2017, 2026))[4])
    assert d["latest_data_date"] == "2026-09-21"


def test_map_cells(client):
    r = client.get("/api/map?bbox=-65,-10,-61,-2&start=2026-01-01&end=2026-09-21")
    assert r.status_code == 200
    d = r.get_json()
    assert d["grid_deg"] == 0.05
    assert abs(sum(c["value"] for c in d["cells"]) - float(JUNE[2026] + SEPT[2026] + 4.0)) < 1e-6


def test_hotspots_rows(client):
    r = client.get("/api/hotspots?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21&page=1&page_size=10")
    assert r.status_code == 200
    d = r.get_json()
    assert d["page_size"] == 10
    # default export/API keeps only the detections that feed the series
    # (all test dates are after the switch, SNPP series): 1 row per date
    assert d["total"] == len(JUNE) + len(SEPT) + 1
    assert len(d["rows"]) == 10
    assert all(row["platform"] == "SNPP" for row in d["rows"])
    assert d["rows"][0]["sensor"] == "VIIRS"


def test_hotspots_all_sensors(client):
    r = client.get("/api/hotspots?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21&all_sensors=1")
    assert r.status_code == 200
    d = r.get_json()
    assert d["total"] == 2 * (len(JUNE) + len(SEPT) + 1)


def test_coverage(client):
    r = client.get("/api/coverage")
    assert r.status_code == 200
    d = r.get_json()
    assert d["regions"][0]["name"] == "test_region"
    assert d["regions"][0]["label"] == "Test Region"
    assert d["regions"][0]["countries"] == ["Bolivia"]
    assert d["starter_areas"] == []


def test_methods(client):
    r = client.get("/api/methods?region=test_region")
    assert r.status_code == 200
    d = r.get_json()
    assert d["calibration"]["k_median"] == 2.5
    assert d["calibration"]["k_min"] == 2.5
    assert d["calibration"]["k_max"] == 2.5
    assert d["calibration"]["count_per_level"] == {"tile_month": 1}
    assert d["validation"]["calibration_years"]["years"] == [2013, 2017]


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


def test_methods_injection_rejected(client):
    r = client.get("/api/methods?region=test_region'%20OR%20'1'='1")
    assert r.status_code == 422
    assert "'" not in r.get_data(as_text=True)


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.headers["Content-Type"].startswith("application/json")


def test_assets_path_traversal(client):
    r = client.get("/assets/..%2F..%2F..%2F.env")
    body = r.get_data(as_text=True)
    assert "FIRMS_MAP_KEY" not in body
    assert "***REMOVED***" not in body


def test_bad_month_is_400(client):
    r = client.get("/api/map?bbox=-65,-10,-61,-2&start=2018-01-01&end=2018-12-31&month=13")
    assert r.status_code == 400
    assert r.get_json()["field"] == "month"


def test_bad_page_is_400(client):
    r = client.get("/api/hotspots?bbox=-65,-10,-61,-2&start=2018-01-01&end=2018-12-31&page=abc")
    assert r.status_code == 400
    assert r.get_json()["field"] == "page"


def test_bad_page_size_is_400(client):
    r = client.get("/api/hotspots?bbox=-65,-10,-61,-2&start=2018-01-01&end=2018-12-31&page_size=xyz")
    assert r.status_code == 400
    assert r.get_json()["field"] == "page_size"


def test_summary_422(client):
    r = client.get("/api/summary?bbox=95,-45,99,-42&start=2003-01-01&end=2018-12-31")
    assert r.status_code == 422


def test_calendar_304_then_data_change(client, env):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21",
                   headers={"If-None-Match": '"dv1"'})
    assert r.status_code == 304
    dv_path = os.path.join(env.DATA_PROCESSED, "data_version.json")
    json.dump({"detections": "dv2", "celldays": "dv2", "harmonized_daily": "dv2"},
              open(dv_path, "w"))
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21",
                   headers={"If-None-Match": '"dv1"'})
    assert r.status_code == 200
    assert r.headers["ETag"] == '"dv2"'


def test_health_stale_with_injected_clock(client, env, monkeypatch):
    # inject a clock 100+ days after the fixture's latest data date -> stale
    monkeypatch.setenv("FIRECAL_TODAY", "2026-12-31")
    r = client.get("/health")
    body = r.get_json()
    assert body["status"] == "stale"
    assert body["regions"][0]["age_days"] == (date(2026, 12, 31) - date(2026, 9, 21)).days
    # clock inside 3 days of the data -> fresh again
    monkeypatch.setenv("FIRECAL_TODAY", "2026-09-22")
    r = client.get("/health")
    assert r.get_json()["status"] == "ok"


def test_calendar_under_50kb(client):
    r = client.get("/api/calendar?bbox=-65,-10,-61,-2&start=2017-01-01&end=2026-09-21")
    assert r.status_code == 200
    assert len(r.get_data()) < 50 * 1024
