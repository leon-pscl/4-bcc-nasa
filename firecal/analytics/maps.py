"""Map cells analytics."""

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings


def map_cells(area: Area, start, end, month=None, settings=None):
    if settings is None:
        settings = Settings()
    grid = settings.GRID_DEG
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{settings.DATA_PROCESSED}/harmonized_daily.parquet')").df()
    con.close()
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    df = df[(df["date_local"] >= start_d) & (df["date_local"] <= end_d)]
    if month:
        y, m = month.split("-")
        df = df[(pd.to_datetime(df["date_local"]).dt.year == int(y)) & (pd.to_datetime(df["date_local"]).dt.month == int(m))]
    mask = [area.contains_cell(int(r["cell_lat_idx"]), int(r["cell_lon_idx"]), grid) for r in df.to_dict("records")]
    df = df[mask]
    agg = df.groupby(["cell_lat_idx", "cell_lon_idx"])["value"].sum().reset_index()
    cells = []
    for r in agg.to_dict("records"):
        lat = (r["cell_lat_idx"] + 0.5) * grid
        lon = (r["cell_lon_idx"] + 0.5) * grid
        cells.append({"lat": float(lat), "lon": float(lon), "value": float(r["value"])})
    aggregated_to = None
    if len(cells) > settings.MAX_MAP_CELLS:
        # aggregate 5x
        factor = 5
        new = {}
        for c in cells:
            key = (round(c["lat"] / (grid * factor)), round(c["lon"] / (grid * factor)))
            new[key] = new.get(key, 0) + c["value"]
        cells = [{"lat": k[0] * grid * factor, "lon": k[1] * grid * factor, "value": v} for k, v in new.items()]
        aggregated_to = grid * factor
    return {"grid_deg": grid, "aggregated_to": aggregated_to, "cells": cells}