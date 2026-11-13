"""Validation metrics for harmonization (C5), computed in DuckDB.

`monthly_modis` is Aqua cell-days x k (not the harmonized table), and VIIRS
outage days are left out of the comparison.
"""

import duckdb
import pandas as pd

from firecal.harmonize.db import _metrics, monthly_sql


def validate(celldays, calibration, settings, harmonized=None):
    cd = celldays.copy()
    if "region" not in cd.columns:
        cd["region"] = "test"
    con = duckdb.connect()
    try:
        con.register("cd", cd)
        con.register("cal_rel", calibration)
        rows = con.execute(
            monthly_sql("cd", "cal_rel", settings.SERIES_START)).fetchall()
    finally:
        con.close()
    rows = [r for r in rows if r[0] == "test"]

    def block(y0, y1):
        sub = [r for r in rows if y0 <= r[1] <= y1]
        per_year = {}
        for y in range(y0, y1 + 1):
            ys = [r for r in sub if r[1] == y]
            m = _metrics([(r[4], r[3]) for r in ys])
            m["monthly_viirs"] = [r[4] for r in ys]
            m["monthly_modis"] = [r[3] for r in ys]
            per_year[str(y)] = m
        agg = _metrics([(r[4], r[3]) for r in sub])
        agg["monthly_viirs"] = [r[4] for r in sub]
        agg["monthly_modis"] = [r[3] for r in sub]
        return {"years": list(range(y0, y1 + 1)), "metrics": agg, "per_year": per_year}

    return {
        "calibration_years": block(*settings.CALIBRATION_YEARS),
        "validation_years": block(*settings.VALIDATION_YEARS),
    }
