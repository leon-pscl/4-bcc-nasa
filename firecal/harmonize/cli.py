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
    # calibration years present?
    years = pd.to_datetime(celldays["date_local"]).dt.year.unique()
    if not (settings.CALIBRATION_YEARS[0] in years):
        raise SystemExit("calibration years not in data; need real archive or devdata? devdata has them")
    calibration = fit_calibration(celldays, settings)
    calibration.to_parquet(proc / "calibration.parquet", index=False)
    harmonized = build_harmonized(celldays, calibration, settings)
    harmonized.to_parquet(proc / "harmonized_daily.parquet", index=False)
    v = validate(celldays, calibration, settings)
    (proc / "validation.json").write_text(json.dumps(v, indent=2))
    print("calibration rows:", len(calibration))
    print("harmonized rows:", len(harmonized))
    return 0


if __name__ == "__main__":
    sys.exit(main())