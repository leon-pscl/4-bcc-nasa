"""CLI for harmonization."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from firecal.config import Settings
from firecal.harmonize.calibrate import fit_calibration
from firecal.harmonize.apply import build_harmonized
from firecal.harmonize.validate import validate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.harmonize")
    args = parser.parse_args(argv)
    settings = Settings()
    proc = Path(settings.DATA_PROCESSED)
    celldays_path = proc / "celldays.parquet"
    if not celldays_path.exists():
        raise SystemExit("celldays.parquet missing")
    celldays = pd.read_parquet(celldays_path)
    # meta check
    meta_path = proc / "celldays.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("grid_deg") != settings.GRID_DEG or meta.get("tile_deg") != settings.TILE_DEG:
            raise SystemExit("celldays.meta.json does not match Settings")
    years = pd.to_datetime(celldays["date_local"]).dt.year.unique()
    for y in range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1):
        if y not in years:
            raise SystemExit("calibration years not in data")
    calibration = fit_calibration(celldays, settings)
    tmp = (proc / "calibration.parquet").with_suffix(".parquet.tmp")
    calibration.to_parquet(tmp, index=False)
    tmp.replace(proc / "calibration.parquet")
    harmonized = build_harmonized(celldays, calibration, settings)
    tmp = (proc / "harmonized_daily.parquet").with_suffix(".parquet.tmp")
    harmonized.to_parquet(tmp, index=False)
    tmp.replace(proc / "harmonized_daily.parquet")
    v = validate(celldays, calibration, settings)
    tmp = (proc / "validation.json").with_suffix(".json.tmp")
    tmp.write_text(json.dumps(v, indent=2))
    tmp.replace(proc / "validation.json")
    print("calibration rows:", len(calibration))
    print("harmonized rows:", len(harmonized))
    return 0


if __name__ == "__main__":
    sys.exit(main())