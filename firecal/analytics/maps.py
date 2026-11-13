"""Map cells analytics."""

import pandas as pd


def map_cells(area, start, end, month=None, harmonized_path=None):
    df = pd.read_parquet(harmonized_path)
    mask = df.apply(lambda r: area.contains_cell(r["cell_lat_idx"], r["cell_lon_idx"]), axis=1)
    df = df[mask]
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    df = df[(df["date_local"] >= pd.to_datetime(start).date()) & (df["date_local"] <= pd.to_datetime(end).date())]
    if month is not None:
        df = df[pd.to_datetime(df["date_local"]).dt.month == month]
    agg = df.groupby(["cell_lat_idx", "cell_lon_idx"]).agg(value=("value", "sum")).reset_index()
    return {"cells": agg.to_dict(orient="records")}