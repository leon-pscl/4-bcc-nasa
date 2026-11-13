"""Post-build integrity checks: these fail loudly when the pipeline is wrong.

(a) calibration: one row per (region, platform, reference, tile_id, month)
(b) harmonized_daily: one row per (region, cell_lat_idx, cell_lon_idx, date_local)
"""

import duckdb
import pandas as pd


def check_calibration(df):
    """Pass a DataFrame (or DuckDB relation name via con)."""
    if isinstance(df, pd.DataFrame):
        dup = df.groupby(["region", "platform", "reference", "tile_id", "month"]).size()
        bad = dup[dup > 1]
        if len(bad):
            raise AssertionError(
                f"calibration: {len(bad)} duplicate (region, platform, reference, tile_id, month) rows; "
                f"e.g. {bad.index[0]} ({bad.iloc[0]} rows)")
        return
    rows = df.fetchall()
    if len(rows) != len(set(rows)):
        raise AssertionError("calibration: duplicate (region, platform, reference, tile_id, month) rows")


def check_harmonized_frame(df):
    if isinstance(df, pd.DataFrame):
        dup = df.groupby(["region", "cell_lat_idx", "cell_lon_idx", "date_local"]).size()
        bad = dup[dup > 1]
        if len(bad):
            raise AssertionError(
                f"harmonized: {len(bad)} duplicate (region, cell_lat_idx, cell_lon_idx, date_local) rows; "
                f"e.g. {bad.index[0]} ({bad.iloc[0]} rows)")
        return
    rows = df.fetchall()
    if len(rows) != len(set(rows)):
        raise AssertionError("harmonized: duplicate (region, cell_lat_idx, cell_lon_idx, date_local) rows")


def check_calibration_sql(con, table):
    n, nd = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT (region, platform, reference, tile_id, month)) "
        f"FROM {table}").fetchone()
    if n != nd:
        raise AssertionError(
            f"calibration: {n} rows but only {nd} distinct "
            "(region, platform, reference, tile_id, month)")


def check_harmonized_sql(con, table):
    n, nd = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT (region, cell_lat_idx, cell_lon_idx, date_local)) "
        f"FROM {table}").fetchone()
    if n != nd:
        raise AssertionError(
            f"harmonized: {n} rows but only {nd} distinct "
            "(region, cell_lat_idx, cell_lon_idx, date_local)")
