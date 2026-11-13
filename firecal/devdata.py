"""Synthetic cell-days for development (isolated, labeled)."""

import argparse
import json
import os
import random

import numpy as np
import pandas as pd

from firecal.config import Settings
from firecal.cells.grid import cell_indices, tile_id


def generate(settings, region="bolivia_east", seed=42):
    rng = random.Random(seed)
    np.random.seed(seed)
    bbox = settings.REGIONS[region]
    w, s, e, n = bbox
    # two tiles
    mid = (w + e) / 2
    tiles_ratio = {0: 2.5, 1: 1.5}
    rows = []
    for year in range(2003, 2027):
        for month in range(1, 13):
            peak = month in (8, 9, 10)
            n_days = 28
            for _ in range(5 + (15 if peak else 0)):
                day = rng.randint(1, n_days)
                tile_idx = 0 if rng.random() < 0.5 else 1
                tile_w = w if tile_idx == 0 else mid
                tile_e = mid if tile_idx == 0 else e
                lat = rng.uniform(s, n)
                lon = rng.uniform(tile_w, tile_e)
                # Aqua all years
                ci, cj = cell_indices(lat, lon, settings.GRID_DEG)
                rows.append({
                    "cell_lat_idx": ci,
                    "cell_lon_idx": cj,
                    "tile_id": tile_id(lat, lon, settings.TILE_DEG),
                    "date_local": pd.Timestamp(year, month, day).date(),
                    "platform": "Aqua",
                    "n_detections": rng.randint(1, 4),
                    "frp_sum": float(rng.uniform(1, 10)),
                })
                # SNPP only from 2012-01-20
                if pd.Timestamp(year, month, day).date() >= pd.Timestamp("2012-01-20").date():
                    if rng.random() < (0.6 if tile_idx == 0 else 0.5):
                        # ratio
                        for _ in range(int(tiles_ratio[tile_idx])):
                            rows.append({
                                "cell_lat_idx": ci,
                                "cell_lon_idx": cj,
                                "tile_id": tile_id(lat, lon, settings.TILE_DEG),
                                "date_local": pd.Timestamp(year, month, day).date(),
                                "platform": "SNPP",
                                "n_detections": rng.randint(1, 4),
                                "frp_sum": float(rng.uniform(1, 10)),
                            })
    df = pd.DataFrame(rows)
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    df["n_detections"] = df["n_detections"].astype("int32")
    df["frp_sum"] = df["frp_sum"].astype("float64")
    df["tile_id"] = df["tile_id"].astype("string")
    df["platform"] = df["platform"].astype("string")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="bolivia_east")
    args = parser.parse_args()
    settings = Settings.from_env()
    out_dir = os.path.join("data", "synthetic")
    os.makedirs(out_dir, exist_ok=True)
    df = generate(settings, args.region)
    out = os.path.join(out_dir, "celldays.parquet")
    df.to_parquet(out, index=False)
    cov = os.path.join(out_dir, "coverage.json")
    with open(cov, "w") as f:
        json.dump([{"name": args.region, "bbox": list(settings.REGIONS[args.region]),
                    "start": "2003-01-01", "end": "2026-12-31",
                    "platforms": ["Aqua", "SNPP"], "latest_date": "2026-12-31",
                    "synthetic": True}], f, indent=2)
    print(f"wrote {len(df)} synthetic cell-days to {out_dir}")


if __name__ == "__main__":
    main()