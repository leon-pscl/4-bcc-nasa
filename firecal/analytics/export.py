"""Export hotspot rows."""

import math

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings


def hotspot_rows(area: Area, start, end, all_sensors=False, settings=None):
    if settings is None:
        settings = Settings()
    det_path = f"{settings.DATA_PROCESSED}/detections.parquet"
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{det_path}')").df()
    con.close()
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    df = df[(df["date_local"] >= start_d) & (df["date_local"] <= end_d)]
    grid = settings.GRID_DEG

    def in_area(row):
        ci = int(math.floor(row["latitude"] / grid))
        cj = int(math.floor(row["longitude"] / grid))
        return area.contains_cell(ci, cj, grid)

    mask = df.apply(in_area, axis=1)
    df = df[mask]
    if not all_sensors:
        switch = pd.to_datetime(settings.SWITCH_DATE).date()

        def keep(row):
            d = row["date_local"]
            if d < switch:
                return row["platform"] == "Aqua"
            return row["platform"] == "SNPP"

        df = df[df.apply(keep, axis=1)]
    cols = ["date_local", "acq_datetime_utc", "latitude", "longitude", "confidence_class", "frp", "daynight", "sensor", "platform", "processing"]
    df = df[cols]
    chunk_size = 1000
    for i in range(0, len(df), chunk_size):
        yield df.iloc[i:i + chunk_size]