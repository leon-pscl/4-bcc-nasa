"""Build cell-days (C2) from detections, in DuckDB.

Same SQL the pipeline runs over the full dataset, so the tested code is the code
that produced the data.
"""

import duckdb
import pandas as pd

from firecal.cells.db import build_celldays_sql
from firecal.contracts import validate_celldays


def validate_meta(meta, settings):
    if meta.get("grid_deg") != settings.GRID_DEG:
        raise ValueError("celldays meta mismatch: grid_deg")
    if meta.get("tile_deg") != settings.TILE_DEG:
        raise ValueError("celldays meta mismatch: tile_deg")
    if list(meta.get("confidence_keep", [])) != list(settings.CONFIDENCE_KEEP):
        raise ValueError("celldays meta mismatch: confidence_keep")
    if list(meta.get("keep_types", [])) != list(settings.KEEP_TYPES):
        raise ValueError("celldays meta mismatch: keep_types")


def build_celldays(detections, settings):
    df = detections.copy()
    if "region" not in df.columns:
        df["region"] = "test"
    con = duckdb.connect()
    try:
        con.register("det", df)
        sql = build_celldays_sql("det", settings.GRID_DEG, settings.TILE_DEG,
                                 settings.CONFIDENCE_KEEP, settings.KEEP_TYPES)
        out = con.execute(sql).df()
    finally:
        con.close()
    if len(out):
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
        out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
        out["n_detections"] = out["n_detections"].astype("int32")
        out["frp_sum"] = out["frp_sum"].astype("float64")
        out["tile_id"] = out["tile_id"].astype("string")
        out["platform"] = out["platform"].astype("string")
    validate_celldays(out)
    return out
