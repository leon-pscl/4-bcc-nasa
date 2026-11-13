"""Build the harmonized daily series (C4) in DuckDB.

Same SQL the pipeline runs over the full dataset, so the tested code is the code
that produced the data.
"""

import duckdb
import pandas as pd

from firecal.contracts import validate_harmonized
from firecal.harmonize.db import harmonized_sql


def build_harmonized(celldays, calibration, settings):
    cd = celldays.copy()
    if "region" not in cd.columns:
        cd["region"] = "test"
    con = duckdb.connect()
    try:
        con.register("cd", cd)
        con.register("cal_final", calibration)
        out = con.execute(
            harmonized_sql("cd", "cal_final", settings.SERIES_START, settings.SWITCH_DATE)
        ).df()
    finally:
        con.close()
    if len(out):
        out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
        out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
        out["tile_id"] = out["tile_id"].astype("string")
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        out["value"] = out["value"].astype("float64")
        out["basis"] = out["basis"].astype("string")
    validate_harmonized(out)
    return out
