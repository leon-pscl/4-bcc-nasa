"""Build cell-days from detections."""

import math

import numpy as np
import pandas as pd

from firecal.cells.grid import cell_indices, tile_id
from firecal.contracts import validate_celldays


def build_celldays(detections, settings):
    df = detections.copy()
    keep_conf = set(settings.CONFIDENCE_KEEP)
    df = df[df["confidence_class"].isin(keep_conf)]
    if "type" in df.columns:
        def keep_type(v):
            if pd.isna(v):
                return True
            return int(v) in set(settings.KEEP_TYPES)
        df = df[df["type"].apply(keep_type)]

    lat = df["latitude"].to_numpy(dtype=float)
    lon = df["longitude"].to_numpy(dtype=float)
    g = settings.GRID_DEG
    t = settings.TILE_DEG
    df = df.copy()
    df["cell_lat_idx"] = np.floor(lat / g).astype("int32")
    df["cell_lon_idx"] = np.floor(lon / g).astype("int32")
    df["tile_id"] = [f"{math.floor(a / t)}_{math.floor(b / t)}" for a, b in zip(lat, lon)]
    grouped = df.groupby(["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform"], dropna=False).agg(
        n_detections=("uid", "count"),
        frp_sum=("frp", "sum"),
    ).reset_index()
    grouped["cell_lat_idx"] = grouped["cell_lat_idx"].astype("int32")
    grouped["cell_lon_idx"] = grouped["cell_lon_idx"].astype("int32")
    grouped["n_detections"] = grouped["n_detections"].astype("int32")
    grouped["frp_sum"] = grouped["frp_sum"].astype("float64")
    grouped["tile_id"] = grouped["tile_id"].astype("string")
    grouped["platform"] = grouped["platform"].astype("string")
    validate_celldays(grouped)
    return grouped


def validate_meta(meta, settings):
    if meta.get("grid_deg") != settings.GRID_DEG:
        raise ValueError("celldays meta mismatch: grid_deg")
    if meta.get("tile_deg") != settings.TILE_DEG:
        raise ValueError("celldays meta mismatch: tile_deg")
    if list(meta.get("confidence_keep", [])) != list(settings.CONFIDENCE_KEEP):
        raise ValueError("celldays meta mismatch: confidence_keep")
    if list(meta.get("keep_types", [])) != list(settings.KEEP_TYPES):
        raise ValueError("celldays meta mismatch: keep_types")