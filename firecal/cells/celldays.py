"""Build cell-days from detections."""

import numpy as np
import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_celldays


def build_celldays(detections: pd.DataFrame, settings: Settings = None) -> pd.DataFrame:
    if settings is None:
        settings = Settings()
    df = detections.copy()
    df = df[df["confidence_class"].isin(settings.CONFIDENCE_KEEP)]
    if "type" in df.columns:
        keep = df["type"].isna() | df["type"].isin(settings.KEEP_TYPES)
        df = df[keep]

    grid = settings.GRID_DEG
    tile = settings.TILE_DEG
    df["cell_lat_idx"] = np.floor(df["latitude"].to_numpy() / grid).astype("int32")
    df["cell_lon_idx"] = np.floor(df["longitude"].to_numpy() / grid).astype("int32")
    df["tile_id"] = (np.floor(df["latitude"].to_numpy() / tile).astype(int).astype(str)
                     + "_" + np.floor(df["longitude"].to_numpy() / tile).astype(int).astype(str))

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