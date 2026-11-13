"""Synthetic cell-days for development."""

import argparse
import os
import sys

import numpy as np
import pandas as pd

from firecal.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="bolivia_east")
    args = parser.parse_args()
    settings = Settings.from_env()
    bbox = settings.REGIONS[args.region]
    w, s, e, n = bbox
    rows = []
    for year in range(2003, 2027):
        for month in range(1, 13):
            # seasonality peak Aug-Oct
            base = 10 + 20 * (month in (8, 9, 10))
            for _ in range(base):
                lat = np.random.uniform(s, n)
                lon = np.random.uniform(w, e)
                from firecal.cells.grid import cell_indices, tile_id
                ci, cj = cell_indices(lat, lon, settings.GRID_DEG)
                rows.append({
                    "cell_lat_idx": ci,
                    "cell_lon_idx": cj,
                    "tile_id": tile_id(lat, lon, settings.TILE_DEG),
                    "date_local": pd.Timestamp(year, month, 15).date(),
                    "platform": np.random.choice(["Aqua", "SNPP"], p=[0.4, 0.6]),
                    "n_detections": 1,
                    "frp_sum": float(np.random.uniform(1, 10)),
                })
    df = pd.DataFrame(rows)
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    df["n_detections"] = df["n_detections"].astype("int32")
    df["frp_sum"] = df["frp_sum"].astype("float64")
    df["tile_id"] = df["tile_id"].astype("string")
    df["platform"] = df["platform"].astype("string")
    out = os.path.join(settings.DATA_PROCESSED, "celldays.parquet")
    os.makedirs(settings.DATA_PROCESSED, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} synthetic cell-days")


if __name__ == "__main__":
    main()