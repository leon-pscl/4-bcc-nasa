"""Build cell-days from detections."""

import math

import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_celldays


def build_celldays(detections: pd.DataFrame, settings: Settings = None) -> pd.DataFrame:
    if settings is None:
        settings = Settings()
    df = detections.copy()
    # confidence filter
    df = df[df["confidence_class"].isin(settings.CONFIDENCE_KEEP)]
    # type filter
    if "type" in df.columns:
        # keep rows where type in KEEP_TYPES or type is null (NRT has no type)
        keep = df["type"].isna() | df["type"].isin(settings.KEEP_TYPES)
        df = df[keep]

    def cell_lat(row):
        return math.floor(row["latitude"] / settings.GRID_DEG)

    def cell_lon(row):
        return math.floor(row["longitude"] / settings.GRID_DEG)

    df["cell_lat_idx"] = df.apply(cell_lat, axis=1).astype("int32")
    df["cell_lon_idx"] = df.apply(cell_lon, axis=1).astype("int32")
    df["tile_id"] = df.apply(lambda r: f"{math.floor(r['latitude'] / settings.TILE_DEG)}_{math.floor(r['longitude'] / settings.TILE_DEG)}", axis=1)

    grouped = df.groupby(["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform"], as_index=False).agg(
        n_detections=("uid", "count"),
        frp_sum=("frp", "sum"),
    )
    grouped["cell_lat_idx"] = grouped["cell_lat_idx"].astype("int32")
    grouped["cell_lon_idx"] = grouped["cell_lon_idx"].astype("int32")
    grouped["n_detections"] = grouped["n_detections"].astype("int32")
    grouped["frp_sum"] = grouped["frp_sum"].astype("float64")
    validate_celldays(grouped)
    return grouped