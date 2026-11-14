"""Terra gap-fill (D20): pre-2012 days where Aqua is blind but Terra is up are
filled with Terra x k_terra, basis 'terra_gapfill'. Hand-worked fixture: one cell,
June 2010. Aqua dies on 2010-06-15 (0 cell-days); Terra was up that day."""

import json

import pandas as pd
import pytest

from firecal.config import Settings


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)

    cols = ["latitude", "longitude", "brightness", "scan", "track", "acq_date",
            "acq_time", "satellite", "instrument", "confidence", "version",
            "bright_t31", "frp", "daynight"]
    rows = []
    AQUA_CELLS = [-4.975, -5.075, -5.175, -5.275, -5.375]  # five cells, a_med >= 5/day
    i = 0
    def add(cell_idx, date, satellite):
        nonlocal i
        lat = AQUA_CELLS[cell_idx] + round((i % 13) * 4e-5, 5)
        lon = -61.975 + ((i * 7) % 25) * 1e-4
        rows.append([lat, lon, 320.0, 1.0, 1.0, date, 1200, satellite, "MODIS",
                     50, "6.1SP", 310.0, 5.0, "D"])
        i += 1
    # aqua: 6 detections per cell per day June 2010, but NO aqua on 2010-06-15
    for d in range(1, 31):
        if d == 15:
            continue
        date = f"2010-06-{d:02d}"
        for c in range(5):
            for _ in range(6):
                add(c, date, "A")
    # terra: 1 in cell 0 for all June 2010, plus 12 on 2010-06-15
    for d in range(1, 31):
        date = f"2010-06-{d:02d}"
        terra_n = 12 if d == 15 else 1
        for _ in range(terra_n):
            add(0, date, "T")
    csv = root / "raw" / "aqua_gap.csv"
    with open(csv, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")

    settings = Settings()
    settings.DATA_RAW = str(root / "raw")
    settings.DATA_PROCESSED = str(root / "processed")
    settings.REGIONS = {"test_region": (-180.0, -90.0, 180.0, 90.0)}
    settings.CALIBRATION_YEARS = (2010, 2010)
    settings.VALIDATION_YEARS = (2010, 2010)
    settings.MIN_CALIBRATION_CELLDAYS = 30
    settings.GRID_DEG = 0.05
    settings.TILE_DEG = 1.0

    from firecal.ingest.db import connect, ingest_files
    con = connect()
    ingest_files(con, [str(csv)], "test_region", (-180.0, -90.0, 180.0, 90.0), settings)

    from firecal.cells.db import rebuild as rebuild_cells
    rebuild_cells(settings, region="test_region")
    from firecal.harmonize.db import rebuild
    rebuild(settings, region="test_region")
    return settings


def test_terra_gapfill_rows(env):
    from firecal.harmonize.db import rebuild
    import duckdb
    rebuilt = rebuild(env, region="test_region")
    assert rebuilt == []  # second rebuild is a no-op (fingerprints unchanged)

    con = duckdb.connect()
    root = f"{env.DATA_PROCESSED}/harmonized_daily/region=test_region/year=2010/*.parquet"
    days = con.execute(f"""
        SELECT date_local, basis, COUNT(*) AS n, SUM(value) AS s
        FROM read_parquet('{root}')
        GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    by_date = {}
    for date, basis, n, s in days:
        by_date.setdefault(str(date)[:10], {})[basis] = (n, s)
    blind = by_date["2010-06-15"]
    assert "terra_gapfill" in blind, f"2010-06-15 should carry terra_gapfill rows, got {blind}"
    assert blind["terra_gapfill"][0] == 1  # one terra cell-day (12 detections in one cell)
    assert blind["terra_gapfill"][1] > 0.0   # scaled by k_terra
    for d, basis in ((d, b) for d, b in by_date.items() if d != "2010-06-15"):
        assert "modis_scaled" in basis
        assert "terra_gapfill" not in basis


def test_terra_calibration_rows(env):
    import duckdb
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT platform, reference, level, COUNT(*) AS n
        FROM read_parquet('{env.DATA_PROCESSED}/calibration.parquet')
        WHERE platform = 'Terra' AND reference = 'Aqua'
        GROUP BY 1,2,3
    """).fetchall()
    assert rows, "Terra calibration rows should exist"
    levels = {r[2] for r in rows}
    assert "all" in levels or "all_month" in levels or "tile_month" in levels


def test_harmonized_unique_with_gapfill(env):
    import duckdb
    con = duckdb.connect()
    harm = f"{env.DATA_PROCESSED}/harmonized_daily/region=test_region/**/*.parquet"
    n, nd = con.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT (cell_lat_idx, cell_lon_idx, date_local))
        FROM read_parquet('{harm}')
    """).fetchone()
    assert n == nd
