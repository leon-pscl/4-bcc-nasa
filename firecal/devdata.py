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
    if region in settings.REGIONS:
        bbox = settings.REGIONS[region]
    elif region in settings.STARTER_AREAS:
        bbox = settings.STARTER_AREAS[region]
    else:
        bbox = {"bolivia_east": (-64, -18, -60, -14), "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738)}[region]
    w, s, e, n = bbox
    # two 1-degree tiles inside the bbox
    tile_specs = [
        ("A", -16.0, -63.0, 2.5),
        ("B", -16.0, -61.0, 1.5),
    ]
    gap_dates = {pd.Timestamp(2016, 9, 10).date(), pd.Timestamp(2016, 9, 20).date()}
    rows = []
    for year in range(2003, 2027):
        for month in range(1, 13):
            seasonal = 3.0 if month in (8, 9, 10) else 1.0
            lam_a = 15.0 * seasonal
            for day in (1, 5, 10, 15, 20, 25):
                d = pd.Timestamp(year, month, day).date()
                for (name, tlat, tlon, ratio) in tile_specs:
                    lat_lo, lat_hi = tlat, tlat + 1.0
                    lon_lo, lon_hi = tlon, tlon + 1.0
                    # clamp to bbox
                    lat_lo = max(lat_lo, s)
                    lat_hi = min(lat_hi, n)
                    lon_lo = max(lon_lo, w)
                    lon_hi = min(lon_hi, e)
                    n_cells = 20
                    aqua_n = int(np.random.poisson(lam_a))
                    aqua_cells = rng.sample(range(n_cells * n_cells), min(aqua_n, n_cells * n_cells))
                    for idx in aqua_cells:
                        i = idx // n_cells
                        j = idx % n_cells
                        lat = lat_lo + (i + 0.5) / n_cells * (lat_hi - lat_lo)
                        lon = lon_lo + (j + 0.5) / n_cells * (lon_hi - lon_lo)
                        ci, cj = cell_indices(lat, lon, settings.GRID_DEG)
                        rows.append({
                            "cell_lat_idx": ci,
                            "cell_lon_idx": cj,
                            "tile_id": tile_id(lat, lon, settings.TILE_DEG),
                            "date_local": d,
                            "platform": "Aqua",
                            "n_detections": int(rng.randint(1, 4)),
                            "frp_sum": float(rng.uniform(1, 10)),
                        })
                    if d >= pd.Timestamp("2012-01-20").date() and d not in gap_dates:
                        snpp_n = int(np.random.poisson(lam_a * ratio))
                        snpp_cells = rng.sample(range(n_cells * n_cells), min(snpp_n, n_cells * n_cells))
                        for idx in snpp_cells:
                            i = idx // n_cells
                            j = idx % n_cells
                            lat = lat_lo + (i + 0.5) / n_cells * (lat_hi - lat_lo)
                            lon = lon_lo + (j + 0.5) / n_cells * (lon_hi - lon_lo)
                            ci, cj = cell_indices(lat, lon, settings.GRID_DEG)
                            rows.append({
                                "cell_lat_idx": ci,
                                "cell_lon_idx": cj,
                                "tile_id": tile_id(lat, lon, settings.TILE_DEG),
                                "date_local": d,
                                "platform": "SNPP",
                                "n_detections": int(rng.randint(1, 4)),
                                "frp_sum": float(rng.uniform(1, 10)),
                            })
    df = pd.DataFrame(rows)
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    df["n_detections"] = df["n_detections"].astype("int32")
    df["frp_sum"] = df["frp_sum"].astype("float64")
    df["tile_id"] = df["tile_id"].astype("string")
    df["platform"] = df["platform"].astype("string")
    # ensure date_local is date
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    return df


def generate_grid_cells(settings, region="bolivia_east", masked=6, seed=42):
    """Synthetic C11 grid_cells (small): a few masked cells, rest kept."""
    import numpy as np
    import pandas as pd
    from firecal.outlook import grid as _grid

    if region in settings.REGIONS:
        bbox = settings.REGIONS[region]
    else:
        bbox = (-64, -18, -60, -14)
    w, s, e, n = bbox
    la_lo, la_hi, lo_lo, lo_hi = _grid.g_index_range(w, s, e, n)
    rows = []
    for la in range(la_lo, la_hi + 1):
        for lo in range(lo_lo, lo_hi + 1):
            rows.append((la, lo))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(rows))
    masked_idx = set(order[:masked].tolist()) if masked else set()
    records = []
    for i, (la, lo) in enumerate(rows):
        is_masked = i in masked_idx
        records.append({
            "region": region,
            "g_lat_idx": np.int32(la), "g_lon_idx": np.int32(lo),
            "center_lat": round(_grid.g_center(la), 4), "center_lon": round(_grid.g_center(lo), 4),
            "fine_cells": np.int8(9),
            "area_km2": np.float64(278.0),
            "water_pct": 99.0 if is_masked else 10.0,
            "barren_pct": 0.0, "snow_ice_pct": 0.0,
            "burnable_pct": 0.5 if is_masked else 80.0,
            "forest_pct": 50.0, "crop_pct": 5.0,
            "keep": not is_masked,
            "mask_reason": "water" if is_masked else "kept",
        })
    return pd.DataFrame.from_records(records)


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