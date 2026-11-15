"""Outlook data tests (steps 2/3 of the 13:50 message).

The reference-number tests derive the grid from the region bbox only; the
mask/monthly/climatology/issue tests use synthetic fixtures in tmp_path and
never touch E:\\datasets.
"""

import math

import numpy as np
import pandas as pd
import pytest

from firecal.config import Settings
from firecal.outlook import grid as grid_mod
from firecal.outlook import surface as surface_mod
from firecal.outlook.cells import build_grid_cells
from firecal.outlook.climatology import build_climatology
from firecal.outlook.issue import issue_month, build_outlook
from firecal.outlook.monthly import build_monthly

SEA_BBOX = (92.0, -11.0, 141.0, 28.5)


def test_g_index_floors_toward_neg_inf():
    assert grid_mod.g_index(-1) == -1
    assert grid_mod.g_index(-3) == -1
    assert grid_mod.g_index(-4) == -2
    assert grid_mod.g_index(-220) == -74
    assert grid_mod.g_index(1840) == 613
    assert grid_mod.g_index(0) == 0


def test_g_index_duckdb_agrees_over_range():
    import duckdb
    con = duckdb.connect()
    lo, hi = -3600, 3600
    rows = con.execute(
        f"SELECT x, CAST(FLOOR(x / 3.0) AS INTEGER) FROM range({lo}, {hi}) t(x)"
    ).fetchall()
    assert len(rows) == hi - lo
    for x, sql_idx in rows:
        assert grid_mod.g_index(int(x)) == int(sql_idx)


def _fine_cells(bbox):
    return surface_mod.fine_cells_for_bbox(bbox)


def test_sea_reference_numbers():
    la, lo = _fine_cells(SEA_BBOX)
    cell_set = set(zip(la.tolist(), lo.tolist()))
    assert len(cell_set) == 774_200
    la_lo, la_hi, lo_lo, lo_hi = grid_mod.g_index_range(*SEA_BBOX)
    rows, cols = la_hi - la_lo + 1, lo_hi - lo_lo + 1
    assert (rows, cols) == (264, 327)
    assert rows * cols == 86_328
    counts = {9: 0, 6: 0, 3: 0, 2: 0}
    area_sum = 0.0
    for g_la in range(la_lo, la_hi + 1):
        for g_lo in range(lo_lo, lo_hi + 1):
            g_la0, g_la1 = grid_mod.fine_range(g_la)
            g_lo0, g_lo1 = grid_mod.fine_range(g_lo)
            fc = sum(1 for x in range(g_la0, g_la1 + 1)
                     for y in range(g_lo0, g_lo1 + 1)
                     if (x, y) in cell_set)
            counts[fc] = counts.get(fc, 0) + 1
            area_sum += grid_mod.cell_area_km2(g_la, g_lo, cell_set)
    assert counts == {9: 85_738, 6: 263, 3: 326, 2: 1}
    assert abs(area_sum - 23_186_978) < 1_000


def test_central_kalimantan_cells():
    ck_bbox = (110.7, -3.6, 115.9, 0.8)
    la_lo, la_hi, lo_lo, lo_hi = grid_mod.g_index_range(*SEA_BBOX)
    cells = [(la, lo)
             for la in range(la_lo, la_hi + 1)
             for lo in range(lo_lo, lo_hi + 1)
             if grid_mod.cell_in_box(la, lo, *ck_bbox)]
    assert len(cells) == 1_015
    assert min(c[0] for c in cells) == -24
    assert max(c[0] for c in cells) == 4
    assert min(c[1] for c in cells) == 738
    assert max(c[1] for c in cells) == 772


def _sg_settings(tmp_path):
    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    settings.REGIONS = {"test_region": (112.05, -3.9, 112.35, -3.75)}
    settings.GRID_DEG, settings.TILE_DEG = 0.05, 1.0
    return settings


def _write_surface(settings, region, rows):
    import os
    from pathlib import Path
    root = Path(settings.DATA_PROCESSED) / "cell_surface" / f"region={region}"
    root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(root / "part-0.parquet", engine="pyarrow", compression="zstd", index=False)
    return df


def _surface_row(la, lo, total, water, barren, snow, burn_max, burn_year):
    return {"region": "test_region", "cell_lat_idx": np.int32(la), "cell_lon_idx": np.int32(lo),
            "total_px": np.int32(total), "water_pct": float(water), "barren_pct": float(barren),
            "snow_ice_pct": float(snow), "burnable_pct_max": float(burn_max),
            "burnable_year_max": np.int16(burn_year)}


def test_mask_fixture_cases(tmp_path):
    settings = _sg_settings(tmp_path)
    rows = []
    # g cell 747: nine all-water fine cells -> masked, water
    for la in (-78, -77, -76):
        for lo in (2241, 2242, 2243):
            rows.append(_surface_row(la, lo, 144, 100.0, 0.0, 0.0, 0.0, 2002))
    # g cell 748: nine cells, barren the largest non-burnable share -> masked, barren
    for la in (-78, -77, -76):
        for lo in (2244, 2245, 2246):
            rows.append(_surface_row(la, lo, 144, 10.0, 80.0, 10.0, 0.0, 2002))
    _write_surface(settings, "test_region", rows)
    df = build_grid_cells(settings, "test_region").set_index(["g_lat_idx", "g_lon_idx"])
    assert not df.loc[(-26, 747), "keep"]
    assert df.loc[(-26, 747), "mask_reason"] == "water"
    assert not df.loc[(-26, 748), "keep"]
    assert df.loc[(-26, 748), "mask_reason"] == "barren"
    assert df.loc[(-26, 747), "fine_cells"] == 9


def test_mask_boundary_and_snow_reason(tmp_path):
    settings = _sg_settings(tmp_path)
    rows = []
    # g cell 747: burnable exactly 5.0 in every fine cell -> kept (>= threshold)
    for la in (-78, -77, -76):
        for lo in (2241, 2242, 2243):
            rows.append(_surface_row(la, lo, 144, 50.0, 25.0, 20.0, 5.0, 2015))
    # g cell 748: snow_ice the largest non-burnable share, burnable 0 -> masked, snow_ice
    for la in (-78, -77, -76):
        for lo in (2244, 2245, 2246):
            rows.append(_surface_row(la, lo, 144, 10.0, 20.0, 70.0, 0.0, 2002))
    _write_surface(settings, "test_region", rows)
    df = build_grid_cells(settings, "test_region").set_index(["g_lat_idx", "g_lon_idx"])
    assert df.loc[(-26, 747), "keep"]
    assert df.loc[(-26, 747), "mask_reason"] == "kept"
    assert not df.loc[(-26, 748), "keep"]
    assert df.loc[(-26, 748), "mask_reason"] == "snow_ice"
    # wetlands are burnable: the burnable set includes IGBP 11
    from firecal.outlook.surface import IGBP_BURNABLE
    assert 11 in IGBP_BURNABLE


def _write_harmonized(settings, region, year, rows):
    from pathlib import Path
    root = Path(settings.DATA_PROCESSED) / "harmonized_daily" / f"region={region}" / f"year={year}"
    root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=["region", "cell_lat_idx", "cell_lon_idx", "tile_id",
                                     "date_local", "value", "basis"])
    df.to_parquet(root / "part-0.parquet", engine="pyarrow", compression="zstd", index=False)


def _write_grid_cells(settings, region, rows):
    from pathlib import Path
    root = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}"
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(root / "part-0.parquet", engine="pyarrow",
                                  compression="zstd", index=False)


def _grid_cell_row(la, lo, keep, reason, area=100.0):
    return {"region": "test_region", "g_lat_idx": np.int32(la), "g_lon_idx": np.int32(lo),
            "center_lat": (la + 0.5) * 0.15, "center_lon": (lo + 0.5) * 0.15,
            "fine_cells": np.int8(9), "area_km2": area,
            "water_pct": 0.0 if keep else 100.0, "barren_pct": 0.0, "snow_ice_pct": 0.0,
            "burnable_pct": 80.0 if keep else 0.0, "forest_pct": 50.0, "crop_pct": 5.0,
            "keep": bool(keep), "mask_reason": reason}


def _c4_row(la, lo, d, value):
    return ("test_region", np.int32(la), np.int32(lo), "t", pd.Timestamp(d).date(),
            float(value), "viirs")


def test_kept_plus_masked_equals_c4_total(tmp_path):
    settings = _sg_settings(tmp_path)
    region = "test_region"
    year = 2020
    # one kept g cell (747, -26) and one masked g cell (748, -26); same fine cells area
    _write_grid_cells(settings, region, [
        _grid_cell_row(-26, 747, True, "kept"),
        _grid_cell_row(-26, 748, False, "water"),
    ])
    rows = []
    # fire inside kept fine cells (lon 2241..2243) and inside masked (lon 2244..2246)
    for d, v in (("2020-09-01", 10.0), ("2020-09-15", 20.0)):
        rows.append(_c4_row(-78, 2241, d, v))
        rows.append(_c4_row(-78, 2244, d, v))
    _write_harmonized(settings, region, year, rows)
    from firecal.dataset import load_state, save_state, partition_key
    state = load_state(settings)
    state.setdefault("harmonized_daily", {})[partition_key(region, year)] = {"fingerprint": "fp-test-1"}
    save_state(settings, state)
    meta = build_monthly(settings, region)
    assert meta["years"][str(year)]["harmonized"] == pytest.approx(60.0)
    assert meta["years"][str(year)]["kept"] == pytest.approx(30.0)
    assert meta["years"][str(year)]["masked"] == pytest.approx(30.0)
    assert meta["years"][str(year)]["harmonized"] == pytest.approx(
        meta["years"][str(year)]["kept"] + meta["years"][str(year)]["masked"])


def test_area_on_grid_lines_equals_calendar_total(tmp_path):
    settings = _sg_settings(tmp_path)
    region = "test_region"
    year = 2021
    _write_grid_cells(settings, region, [
        _grid_cell_row(-26, 747, True, "kept"),
        _grid_cell_row(-26, 748, True, "kept"),
    ])
    rows = [
        _c4_row(-78, 2241, "2021-09-01", 3.0),
        _c4_row(-77, 2242, "2021-09-02", 4.0),
        _c4_row(-78, 2245, "2021-09-03", 5.0),
        _c4_row(-76, 2246, "2021-10-01", 6.0),
    ]
    _write_harmonized(settings, region, year, rows)
    from firecal.dataset import load_state, save_state, partition_key
    state = load_state(settings)
    state.setdefault("harmonized_daily", {})[partition_key(region, year)] = {"fingerprint": "fp-test-2"}
    save_state(settings, state)
    meta = build_monthly(settings, region)
    assert meta["years"][str(year)]["kept"] == pytest.approx(18.0)
    assert meta["years"][str(year)]["masked"] == pytest.approx(0.0)
    # read back the written partition and reconcile against C4
    import duckdb
    con = duckdb.connect()
    m_root = __import__("pathlib").Path(settings.DATA_PROCESSED) / "monthly_cells"
    tot = con.execute(
        f"SELECT SUM(value) FROM read_parquet('{m_root.as_posix()}/region={region}/**/*.parquet')"
    ).fetchone()[0]
    con.close()
    assert tot == pytest.approx(18.0)


def _write_monthly_cells(settings, region, year, rows):
    from pathlib import Path
    root = Path(settings.DATA_PROCESSED) / "monthly_cells" / f"region={region}" / f"year={year}"
    root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=["region", "year", "month", "g_lat_idx", "g_lon_idx",
                                     "value", "value_forest", "value_farmland",
                                     "value_other", "fine_celldays"])
    df.to_parquet(root / "part-0.parquet", engine="pyarrow", compression="zstd", index=False)


def _mc_row(year, month, la, lo, value):
    return ("test_region", np.int16(year), np.int8(month), np.int32(la), np.int32(lo),
            float(value), 0.0, 0.0, 0.0, 1)


def _five_year_fixture(settings, region="test_region"):
    """4 kept cells at a 2x2 block edge: center fire in 3 of 5 VIIRS years."""
    settings.OUTLOOK_PFIRE_START = 2021  # -> VIIRS window 2021-2025
    _write_grid_cells(settings, region, [
        _grid_cell_row(0, 0, True, "kept"),
        _grid_cell_row(0, 1, True, "kept"),
        _grid_cell_row(1, 0, True, "kept"),
        _grid_cell_row(1, 1, True, "kept"),
    ])
    for year in (2021, 2022, 2023, 2024, 2025):
        rows = []
        # cell (0,0): fire in 3 of 5 years
        if year in (2021, 2023, 2025):
            rows.append(_mc_row(year, 9, 0, 0, 10.0))
        # cell (0,1): fire in 1 of 5 years
        if year == 2022:
            rows.append(_mc_row(year, 9, 0, 1, 5.0))
        # cells (1,0) and (1,1): no fire
        if rows:
            _write_monthly_cells(settings, region, year, rows)
    return settings


def test_climatology_p_fire_shrunk_3_of_5(tmp_path):
    settings = _sg_settings(tmp_path)
    region = "test_region"
    _five_year_fixture(settings, region)
    df = build_climatology(settings, region, "2025-12-31")
    row = df[(df.g_lat_idx == 0) & (df.g_lon_idx == 0) & (df.month == 9)].iloc[0]
    # 3 of 5 VIIRS years; p_nbr = mean(self 0.6, neighbour 0.2, 0, 0) = 0.2; m = 3
    assert row.p_fire == pytest.approx(0.45, abs=1e-9)
    row_nbr = df[(df.g_lat_idx == 0) & (df.g_lon_idx == 1) & (df.month == 9)].iloc[0]
    assert row_nbr.p_fire == pytest.approx((1 + 3 * 0.2) / 8, abs=1e-9)


def test_climatology_never_reads_target_year(tmp_path):
    settings = _sg_settings(tmp_path)
    region = "test_region"
    # 2026 rows with enormous values must not move climatology for a 2026-11-14 latest date
    _five_year_fixture(settings, region)
    _write_monthly_cells(settings, region, 2026,
                         [_mc_row(2026, 9, 0, 0, 99999.0), _mc_row(2026, 9, 0, 1, 99999.0)])
    df = build_climatology(settings, region, "2026-11-14")
    assert set(df.baseline_last) == {2025}
    row = df[(df.g_lat_idx == 0) & (df.g_lon_idx == 0) & (df.month == 9)].iloc[0]
    assert row.p_fire == pytest.approx(0.45, abs=1e-9)
    # and with latest_date 2026-12-31 the baseline extends to 2026 (it is complete)
    df2 = build_climatology(settings, region, "2026-12-31")
    assert set(df2.baseline_last) == {2026}


def test_issue_month_and_targets():
    issued, leads = issue_month("2026-11-14")
    assert issued == "2026-10"
    assert leads == [(2026, 11, 1), (2026, 12, 2), (2027, 1, 3)]
    issued, leads = issue_month("2026-11-30")
    assert issued == "2026-11"
    assert leads == [(2026, 12, 1), (2027, 1, 2), (2027, 2, 3)]
