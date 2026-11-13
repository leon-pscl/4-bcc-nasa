"""CLI for firecal.cells."""

import json
import os
import sys

import pandas as pd

from firecal.config import Settings
from firecal.cells.celldays import build_celldays


def main():
    settings = Settings.from_env()
    store_path = os.path.join(settings.DATA_PROCESSED, "detections.parquet")
    out_path = os.path.join(settings.DATA_PROCESSED, "celldays.parquet")
    meta_path = os.path.join(settings.DATA_PROCESSED, "celldays.meta.json")
    if not os.path.exists(store_path):
        print("no detections store")
        sys.exit(1)
    det = pd.read_parquet(store_path)
    cd = build_celldays(det, settings)
    cd.to_parquet(out_path, index=False)
    meta = {
        "grid_deg": settings.GRID_DEG,
        "tile_deg": settings.TILE_DEG,
        "confidence_keep": list(settings.CONFIDENCE_KEEP),
        "keep_types": list(settings.KEEP_TYPES),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote {len(cd)} cell-days")


if __name__ == "__main__":
    main()