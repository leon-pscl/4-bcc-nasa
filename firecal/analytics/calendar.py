"""Calendar analytics."""

import pandas as pd


def calendar_matrix(area, start, end, today, harmonized_path, grid_deg=0.05):
    df = pd.read_parquet(harmonized_path)
    # filter area
    mask = df.apply(lambda r: area.contains_cell(r["cell_lat_idx"], r["cell_lon_idx"]), axis=1)
    df = df[mask]
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df["month"] = pd.to_datetime(df["date_local"]).dt.month
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    df = df[(df["date_local"] >= start_d) & (df["date_local"] <= end_d)]

    # matrix
    years = sorted(set(df["year"]))
    months = list(range(1, 13))
    matrix = {}
    for y in years:
        matrix[y] = {}
        for m in months:
            sub = df[(df["year"] == y) & (df["month"] == m)]
            val = float(sub["value"].sum()) if len(sub) else None
            matrix[y][m] = val

    # partial
    partial = None
    end_ts = pd.to_datetime(end).date()
    if end_ts.day < 28:  # simplified
        partial = {"year": end_ts.year, "month": end_ts.month, "through_day": end_ts.day}

    return {"matrix": matrix, "partial": partial}