"""CLI for firecal.cells."""

import json
import os
import sys
import time

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
    # atomic parquet
    tmp_parquet = out_path + ".tmp"
    cd.to_parquet(tmp_parquet, index=False)
    os.replace(tmp_parquet, out_path)
    meta = {
        "grid_deg": settings.GRID_DEG,
        "tile_deg": settings.TILE_DEG,
        "confidence_keep": list(settings.CONFIDENCE_KEEP),
        "keep_types": list(settings.KEEP_TYPES),
        "build_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_row_count": len(det),
    }
    tmp_meta = meta_path + ".tmp"
    with open(tmp_meta, "w") as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp_meta, meta_path)
    print(f"wrote {len(cd)} cell-days")


if __name__ == "__main__":
    main()