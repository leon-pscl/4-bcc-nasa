"""CLI for firecal.harmonize."""

import os
import sys

import pandas as pd

from firecal.config import Settings
from firecal.harmonize.calibrate import fit_calibration
from firecal.harmonize.apply import build_harmonized


def main():
    settings = Settings.from_env()
    cd_path = os.path.join(settings.DATA_PROCESSED, "celldays.parquet")
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    harm_path = os.path.join(settings.DATA_PROCESSED, "harmonized.parquet")
    if not os.path.exists(cd_path):
        print("no celldays")
        sys.exit(1)
    cd = pd.read_parquet(cd_path)
    cal = fit_calibration(cd, settings)
    cal.to_parquet(cal_path, index=False)
    harm = build_harmonized(cd, cal, settings)
    harm.to_parquet(harm_path, index=False)
    print(f"calibration rows: {len(cal)}, harmonized rows: {len(harm)}")


if __name__ == "__main__":
    main()