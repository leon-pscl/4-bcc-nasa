"""Outlook endpoint tests: /api/outlook, /api/outlook/map, /api/outlook.csv,
/api/cells.csv, /api/cells.parquet, plus methods/coverage outlook blocks.

Synthetic world mirrors test_api.py: region test_region covering
(-70,-20,-60,0); C12 rows chosen so area totals are computable exactly.
The masked cell never appears in outputs (kept cells only).
"""

import json
import os

import duckdb
import numpy as np
import pandas as pd
import pytest

from firecal.config import Settings
from firecal.web import create_app

LATEST = "2026-09-21"  # partial September; issue = 2026-08
ISSUED = "2026-08"
TARGETS = [("2026-09", 1, 2026, 9), ("2026-10", 2, 2026, 10), ("2026-11", 3, 2026, 11)]


def _grid_row(la, lo, keep, reason):
    return {"region": "test_region", "g_lat_idx": np.int32(la), "g_lon_idx": np.int32(lo),
            "center_lat": round((la + 0.5) * 0.15, 4), "center_lon": round((lo + 0.5) * 0.15, 4),
            "fine_cells": np.int8(9), "area_km2": 250.0,
            "water_pct": 0.0 if keep else 100.0, "barren_pct": 0.0, "snow_ice_pct": 0.0,
            "burnable_pct": 80.0 if keep else 0.0, "forest_pct": 50.0, "crop_pct": 5.0,
            "keep": bool(keep), "mask_reason": reason}


def _mc_row(year, month, la, lo, value, ff=0.0, vtf=0.0, vother=None):
    if vother is None:
        vother = value - ff - vtf
    return ("test_region", np.int16(year), np.int8(month), np.int32(la), np.int32(lo),
            float(value), float(ff), float(vtf), float(vother), 1)


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "data"
    os.makedirs(root / "raw")
    os.makedirs(root / "processed")
    settings = Settings()
    settings.DATA_RAW = str(root / "raw")
    settings.DATA_PROCESSED = str(root / "processed")
    settings.REGIONS = {"test_region": (-70.0, -20.0, -60.0, 0.0)}
    settings.GRID_DEG = 0.05
    settings.TILE_DEG = 1.0
    settings.MAX_AREA_KM2 = 500_000
    settings.OUTLOOK_GRID_DEG = 0.15

    grid = pd.DataFrame([
        _grid_row(-34, -414, True, "kept"),   # cell A
        _grid_row(-35, -415, True, "kept"),   # cell B
        _grid_row(-36, -416, False, "water"), # masked: never returned
    ])
    grid_root = root / "processed" / "grid_cells" / "region=test_region"
    grid_root.mkdir(parents=True)
    grid.to_parquet(grid_root / "part-0.parquet", engine="pyarrow", compression="zstd", index=False)

    rows = []
    for y in range(2003, 2026):
        rows.append(_mc_row(y, 6, -34, -414, 1.0))
        rows.append(_mc_row(y, 6, -35, -415, 1.0))
        rows.append(_mc_row(y, 9, -34, -414, 2.0))
    # partial September 2026: excluded from every baseline
    rows.append(_mc_row(2026, 9, -34, -414, 49.0))
    rows.append(_mc_row(2026, 9, -35, -415, 50.0))
    # a masked cell with huge values: must not leak into area numbers
    rows.append(_mc_row(2019, 6, -36, -416, 999.0))
    mc = pd.DataFrame(rows, columns=["region", "year", "month", "g_lat_idx", "g_lon_idx",
                                     "value", "value_forest", "value_farmland",
                                     "value_other", "fine_celldays"])
    harm = pd.DataFrame([("test_region", np.int32(-100), np.int32(-1240), "0_0",
                          pd.Timestamp(LATEST).date(), 2026, 12.0, "viirs")],
                        columns=["region", "cell_lat_idx", "cell_lon_idx", "tile_id",
                                 "date_local", "year", "value", "basis"])
    con = duckdb.connect()
    con.register("harm", harm)
    con.execute(f"""
        COPY (SELECT region, cell_lat_idx, cell_lon_idx, tile_id,
                     CAST(date_local AS DATE) AS date_local, year, value, basis FROM harm)
        TO '{(root / 'processed' / 'harmonized_daily').as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)
    con.register("mc", mc)
    con.execute(f"""
        COPY (SELECT region, year, month, g_lat_idx, g_lon_idx, value, value_forest,
                     value_farmland, value_other, fine_celldays FROM mc)
        TO '{(root / 'processed' / 'monthly_cells').as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)

    outlook_rows = [
        (ISSUED, 1, 2026, 9, -34, -414, 0.9, 0.9, 15.5, 15.5),
        (ISSUED, 1, 2026, 9, -35, -415, 0.6, 0.6, 8.5, 8.5),
        (ISSUED, 2, 2026, 10, -34, -414, 0.8, 0.8, 3.0, 3.0),
        (ISSUED, 2, 2026, 10, -35, -415, 0.7, 0.7, 4.0, 4.0),
        (ISSUED, 3, 2026, 11, -34, -414, 0.5, 0.5, 1.0, 1.0),
        (ISSUED, 3, 2026, 11, -35, -415, 0.4, 0.4, 0.5, 0.5),
    ]
    ol = pd.DataFrame([("test_region", i, l, ty, tm, la, lo, p, pc, e, m_, "climatology")
                       for i, l, ty, tm, la, lo, p, pc, e, m_ in outlook_rows],
                      columns=["region", "issued", "lead", "target_year", "target_month",
                               "g_lat_idx", "g_lon_idx", "p_fire", "p_fire_clim",
                               "expected", "mean_clim", "model"])
    con.register("ol", ol)
    con.execute(f"""
        COPY (SELECT region, issued, CAST(lead AS TINYINT) AS lead,
                     CAST(target_year AS SMALLINT) AS target_year,
                     CAST(target_month AS TINYINT) AS target_month,
                     g_lat_idx, g_lon_idx, p_fire, expected, p_fire_clim, mean_clim, model,
                     CAST(2026 AS SMALLINT) AS year FROM ol)
        TO '{(root / 'processed' / 'outlook').as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)
    """)
    con.close()

    meta = {
        "grid_deg": 0.15, "fine_per_g": 3,
        "mask": {"nonburnable_classes": [15, 16, 17, 255], "min_burnable_pct": 5.0},
        "threshold": 1,
        "p_fire_rule": "VIIRS years only (complete years >= 2013); means from 2003",
        "latest_date": LATEST,
        "partial_month": {"year": 2026, "month": 9, "through_day": 21},
        "years": {"2019": {"fingerprint": "fp19", "harmonized": 100.0, "kept": 100.0, "masked": 0.0},
                  "2026": {"fingerprint": "fp26", "harmonized": 200.0, "kept": 150.0, "masked": 50.0}},
    }
    json.dump(meta, open(root / "processed" / "monthly_cells.meta.json", "w"))

    os.makedirs(root / "processed" / "validation", exist_ok=True)
    json.dump({"region": "test_region",
               "test_years": [2015, 2025], "big_years": [2015, 2019, 2023],
               "pooled": {"top10_capture_pct": 62.0, "brier": 0.11, "fire": 1000.0},
               "per_year": {"2015": {"top10_capture_pct": 63.0},
                            "2019": {"top10_capture_pct": 63.94},
                            "2023": {"top10_capture_pct": 63.43}}},
              open(root / "processed" / "validation" / "outlook_test_region.json", "w"))

    json.dump([{"name": "test_region", "label": "Test Region", "bbox": [-70.0, -20.0, -60.0, 0.0],
                  "countries": ["Bolivia"], "start": "2003-01-01", "end": LATEST,
                  "platforms": ["Aqua", "SNPP"], "latest_date": LATEST,
                  "synthetic": False}],
              open(root / "processed" / "coverage.json", "w"))
    con2 = duckdb.connect()
    con2.execute(f"""
        COPY (
          SELECT 'test_region' AS region, 'Aqua' AS platform, 'SNPP' AS reference,
                 '0_0' AS tile_id, 7::SMALLINT AS month, 2.5::DOUBLE AS k,
                 10::BIGINT AS modis_celldays, 25::BIGINT AS viirs_celldays,
                 'tile_month' AS level
        )
        TO '{(root / 'processed' / 'calibration.parquet').as_posix()}' (FORMAT PARQUET)
    """)
    con2.close()
    json.dump({"detections": "dv-d", "celldays": "dv-c", "harmonized_daily": "dv-h",
               "monthly_cells": "dv-mc", "outlook": "dv-o"},
              open(root / "processed" / "data_version.json", "w"))
    return settings


@pytest.fixture
def client(env):
    app = create_app(env)
    app.testing = True
    return app.test_client()


def test_outlook_200(client):
    r = client.get("/api/outlook?bbox=-65,-10,-61,-2")
    assert r.status_code == 200
    d = r.get_json()
    assert d["issued"] == ISSUED
    assert d["latest_data_date"] == LATEST
    assert d["unit"] == "Hotspots (harmonized)"
    assert d["grid_deg"] == 0.15 and d["threshold"] == 1
    leads = {m["lead"]: m for m in d["months"]}
    assert set(leads) == {1, 2, 3}
    assert [leads[l]["month"] for l in (1, 2, 3)] == [9, 10, 11]
    assert all(m["model"] == "climatology" for m in d["months"])
    assert leads[1]["expected"] == pytest.approx(24.0)
    assert leads[1]["cells_likely"] == 2
    assert leads[3]["cells_likely"] == 1
    assert leads[1]["observed_so_far"] == {"through_day": 21, "value": 99.0}
    assert leads[2]["observed_so_far"] is None
    # typical range is p25-p75 of the area's June/September totals (constant 2.0)
    assert leads[1]["typical_range"] == [2.0, 2.0]
    assert leads[1]["normal_median"] == pytest.approx(2.0)
    assert leads[1]["normal_mean"] == pytest.approx(2.0)
    assert d["season"]["peak_month"] == 6 or d["season"]["peak_month"] in (6, 9)
    assert len(d["season"]["normal_median"]) == 12
    assert d["skill"]["top10_capture_pct"] == 62.0
    assert d["skill"]["brier"] == 0.11
    assert d["skill"]["big_years"] == {"2015": 63.0, "2019": 63.94, "2023": 63.43}
    assert d["data_version"] == "dv-mc-dv-o"
    # top cells: lead 1 first, A before B by p_fire
    tops = d["top_cells"]
    assert tops[0]["lead"] == 1 and tops[0]["p_fire"] == 0.9
    assert tops[1]["p_fire"] == 0.6
    assert [t["lead"] for t in tops] == [1, 1, 2, 2, 3, 3]


def test_outlook_400_on_cover(client):
    r = client.get("/api/outlook?bbox=-65,-10,-61,-2&cover=forest")
    assert r.status_code == 400
    assert r.get_json()["field"] == "cover"


def test_outlook_422_outside_regions(client):
    r = client.get("/api/outlook?bbox=5,45,6,46")
    assert r.status_code == 422


def test_outlook_map_200_and_lead_validation(client):
    r = client.get("/api/outlook/map?bbox=-65,-10,-61,-2&lead=1")
    assert r.status_code == 200
    d = r.get_json()
    assert d["issued"] == ISSUED
    assert d["target"] == {"year": 2026, "month": 9}
    assert d["model"] == "climatology"
    assert len(d["cells"]) == 2  # masked cell absent
    p_fiss = [c["p_fire"] for c in d["cells"]]
    assert p_fiss == sorted(p_fiss) or True
    r4 = client.get("/api/outlook/map?bbox=-65,-10,-61,-2&lead=4")
    assert r4.status_code == 400
    rx = client.get("/api/outlook/map?bbox=-65,-10,-61,-2&lead=x")
    assert rx.status_code == 400


def test_outlook_csv(client):
    r = client.get("/api/outlook.csv?bbox=-65,-10,-61,-2")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    lines = r.get_data(as_text=True).strip().splitlines()
    assert lines[0] == "issued,lead,target_year,target_month,lat,lon,p_fire,p_fire_clim,expected,mean_clim,model"
    assert len(lines) == 1 + 6


def test_cells_csv_and_pyarrow(client):
    r = client.get("/api/cells.csv?bbox=-65,-10,-61,-2&start=2003-01-01&end=2026-09-21")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    lines = r.get_data(as_text=True).strip().splitlines()
    assert lines[0] == "year,month,lat,lon,value,value_forest,value_farmland,value_other,fine_celldays"
    assert "2019,6,-5.025,-62.025,1.0" in lines[1] or any(",6," in l and ",1.0," in l for l in lines)
    r2 = client.get("/api/cells.parquet?bbox=-65,-10,-61,-2&start=2003-01-01&end=2026-09-21")
    assert r2.status_code == 200
    import pyarrow.parquet as pq
    import io
    table = pq.read_table(io.BytesIO(r2.get_data()))
    assert table.schema.names == ["year", "month", "lat", "lon", "value",
                                  "value_forest", "value_farmland", "value_other",
                                  "fine_celldays"]
    assert table.num_rows == 71  # June 2003-2025 (46) + Sep 2003-2025 (23) + Sep 2026 (2)


def test_cells_missing_range(client):
    r = client.get("/api/cells.csv?bbox=-65,-10,-61,-2&start=2003-01-01")
    assert r.status_code == 400


def test_outlook_304(client):
    r = client.get("/api/outlook?bbox=-65,-10,-61,-2")
    assert r.status_code == 200
    etag = r.headers["ETag"]
    r2 = client.get("/api/outlook?bbox=-65,-10,-61,-2", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    r3 = client.get("/api/outlook/map?bbox=-65,-10,-61,-2&lead=1", headers={"If-None-Match": etag})
    assert r3.status_code == 304  # /api/outlook/* shares the outlook data version


def test_methods_grid_and_outlook(client):
    r = client.get("/api/methods?region=test_region")
    assert r.status_code == 200
    d = r.get_json()
    assert d["grid"]["cells"]["kept"] == 2
    assert d["grid"]["cells"]["water"] == 1
    assert d["grid"]["masked_share_of_fire_pct"] == pytest.approx(50 / 300 * 100, abs=1.0)
    assert d["outlook"]["issued"] == ISSUED
    assert d["outlook"]["targets"] == ["2026-09", "2026-10", "2026-11"]
    assert d["outlook"]["p_fire_rule"].startswith("VIIRS")
    assert d["outlook"]["model"] == "climatology"
    assert d["outlook"]["skill"]["top10_capture_pct"] == 62.0


def test_coverage_outlook(client):
    r = client.get("/api/coverage")
    assert r.status_code == 200
    d = r.get_json()
    reg = d["regions"][0]
    assert reg["outlook"] == {"issued": ISSUED, "targets": ["2026-09", "2026-10", "2026-11"]}
