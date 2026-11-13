"""Calibration factors MODIS -> VIIRS (C3), computed in DuckDB.

The pandas-free path: the cell-day frame is registered as a DuckDB view and the
factor table comes from `firecal.harmonize.db.calibration_sql`, the same SQL the
pipeline runs over the full dataset.
"""

import duckdb
import pandas as pd

from firecal.contracts import validate_calibration
from firecal.harmonize.db import calibration_all_sql, calibration_sql


def _con_with(df, name):
    con = duckdb.connect()
    con.register(name, df)
    return con


def fit_calibration(celldays, settings):
    """k = SNPP cell-days / Aqua cell-days per tile x month, with fallbacks."""
    cd = celldays.copy()
    if "region" not in cd.columns:
        cd["region"] = "test"
    if "year" not in cd.columns:
        cd["year"] = pd.to_datetime(cd["date_local"]).dt.year
    cal_years = settings.CALIBRATION_YEARS
    if not len(cd):
        raise ValueError("no calibration years present in data")
    con = _con_with(cd, "cd")
    try:
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_raw AS "
                    f"{calibration_sql('cd', cal_years, settings.MIN_CALIBRATION_CELLDAYS)}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_all AS "
                    f"{calibration_all_sql('cal_raw', settings.MIN_CALIBRATION_CELLDAYS)}")
        out = con.execute("""
            SELECT region, tile_id, CAST(month AS SMALLINT) AS month, k,
                   CAST(modis_celldays AS BIGINT) AS modis_celldays,
                   CAST(viirs_celldays AS BIGINT) AS viirs_celldays, level
            FROM (SELECT * FROM cal_raw UNION ALL SELECT * FROM cal_all)
        """).df()
    finally:
        con.close()
    if not len(out):
        raise ValueError("no calibration years present in data")
    out["tile_id"] = out["tile_id"].astype("string")
    out["region"] = out["region"].astype("string")
    out["month"] = out["month"].astype("int8")
    out["k"] = out["k"].astype("float64")
    out["modis_celldays"] = out["modis_celldays"].astype("int64")
    out["viirs_celldays"] = out["viirs_celldays"].astype("int64")
    out["level"] = out["level"].astype("string")
    validate_calibration(out)
    return out
