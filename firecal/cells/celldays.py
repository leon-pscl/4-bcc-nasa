"""Build cell-days from detections."""

import pandas as pd

from firecal.cells.grid import cell_indices, tile_id
from firecal.contracts import validate_celldays


def build_celldays(detections, settings):
    df = detections.copy()
    # confidence filter
    keep_conf = set(settings.CONFIDENCE_KEEP)
    df = df[df["confidence_class"].isin(keep_conf)]
    # type filter
    if "type" in df.columns:
        def keep_type(v):
            if pd.isna(v):
                return True
            return int(v) in set(settings.KEEP_TYPES)
        df = df[df["type"].apply(keep_type)]
    # cell indices
    glat = []
    glon = []
    tiles = []
    for _, r in df.iterrows():
        ci, cj = cell_indices(r["latitude"], r["longitude"], settings.GRID_DEG)
        glat.append(ci)
        glon.append(cj)
        tiles.append(tile_id(r["latitude"], r["longitude"], settings.TILE_DEG))
    df["cell_lat_idx"] = glat
    df["cell_lon_idx"] = glon
    df["tile_id"] = tiles
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