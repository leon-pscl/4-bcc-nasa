"""CLI for building celldays.parquet."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from firecal.config import Settings
from firecal.cells.celldays import build_celldays


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.cells")
    args = parser.parse_args(argv)
    settings = Settings()
    store = Path(settings.DATA_PROCESSED) / "detections.parquet"
    if not store.exists():
        raise SystemExit("detections.parquet missing; run ingest first")
    det = pd.read_parquet(store)
    cd = build_celldays(det, settings)
    out = Path(settings.DATA_PROCESSED) / "celldays.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    cd.to_parquet(tmp, index=False)
    tmp.replace(out)
    meta = {
        "grid_deg": settings.GRID_DEG,
        "tile_deg": settings.TILE_DEG,
        "filters": {
            "confidence_keep": list(settings.CONFIDENCE_KEEP),
            "keep_types": list(settings.KEEP_TYPES),
        },
        "source_rows": int(len(det)),
        "build_time": __import__("datetime").datetime.utcnow().isoformat(),
    }
    (Path(settings.DATA_PROCESSED) / "celldays.meta.json").write_text(json.dumps(meta, indent=2))
    print("celldays rows:", len(cd))
    return 0


if __name__ == "__main__":
    sys.exit(main())