"""Generate a labeled synthetic celldays dataset for development."""

import argparse
import json
import math
import random
from datetime import date
from pathlib import Path

import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_celldays


def generate(region, settings=None):
    if settings is None:
        settings = Settings()
    bbox = settings.REGIONS[region]
    w, s, e, n = bbox
    tiles = []
    lat = math.floor(s / settings.TILE_DEG)
    while lat * settings.TILE_DEG < n:
        lon = math.floor(w / settings.TILE_DEG)
        while lon * settings.TILE_DEG < e:
            tiles.append(f"{lat}_{lon}")
            lon += 1
        lat += 1
    if not tiles:
        tiles = ["0_0"]

    start = pd.to_datetime(settings.SERIES_START).date()
    end = date.today()
    rows = []
    rng = random.Random(42)
    grid_per_tile = int(settings.TILE_DEG / settings.GRID_DEG)
    for tile in tiles:
        ratio = rng.uniform(1.4, 2.6)
        la, lo = tile.split("_")
        base_cell_lat = int(la) * grid_per_tile
        base_cell_lon = int(lo) * grid_per_tile
        for d in pd.date_range(start, end, freq="D"):
            month = d.month
            season = 1.0 + 2.0 * (month in (8, 9, 10))
            if not (rng.random() < 0.05 * season):
                continue
            if rng.random() < 0.6:
                rows.append((base_cell_lat, base_cell_lon, tile, d.date(), "Aqua"))
            if rng.random() < min(0.9, 0.3 * ratio * season / 2):
                rows.append((base_cell_lat, base_cell_lon, tile, d.date(), "SNPP"))

    df = pd.DataFrame(rows, columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform"])
    df["n_detections"] = 1
    df["n_detections"] = df["n_detections"].astype("int32")
    df["frp_sum"] = 1.0
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    df["cell_lat_idx"] = df["cell_lat_idx"].astype("int32")
    df["cell_lon_idx"] = df["cell_lon_idx"].astype("int32")
    validate_celldays(df[["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform", "n_detections", "frp_sum"]])
    return df[["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform", "n_detections", "frp_sum"]]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.devdata")
    parser.add_argument("--region", default="bolivia_east")
    args = parser.parse_args(argv)
    settings = Settings()
    df = generate(args.region, settings)
    out_dir = Path(settings.DATA_PROCESSED)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "celldays.parquet"
    tmp = out.with_suffix(out.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out)
    cov_path = out_dir / "coverage.json"
    cov = [{"name": args.region, "bbox": [round(float(x), 4) for x in settings.REGIONS[args.region]], "start": settings.SERIES_START, "end": date.today().isoformat(), "platforms": ["Aqua", "SNPP"], "latest_date": date.today().isoformat(), "synthetic": True}]
    cov_path.write_text(json.dumps(cov, indent=2))
    print("synthetic celldays rows:", len(df))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())