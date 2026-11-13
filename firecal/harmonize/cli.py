"""CLI for firecal.harmonize."""

import json
import os
import sys
import time

import pandas as pd

from firecal.config import Settings
from firecal.cells.celldays import validate_meta
from firecal.harmonize.calibrate import fit_calibration
from firecal.harmonize.apply import build_harmonized
from firecal.harmonize.validate import validate


def main():
    settings = Settings.from_env()
    cd_path = os.path.join(settings.DATA_PROCESSED, "celldays.parquet")
    meta_path = os.path.join(settings.DATA_PROCESSED, "celldays.meta.json")
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    harm_path = os.path.join(settings.DATA_PROCESSED, "harmonized_daily.parquet")
    val_path = os.path.join(settings.DATA_PROCESSED, "validation.json")
    if not os.path.exists(cd_path):
        print("no celldays")
        sys.exit(1)
    cd = pd.read_parquet(cd_path)
    if os.path.exists(meta_path):
        import json as _j
        meta = _j.load(open(meta_path))
        validate_meta(meta, settings)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    val = validate(cd, cal, settings, harm)
    # atomic writes
    for path, obj in [(cal_path, cal), (harm_path, harm)]:
        tmp = path + ".tmp"
        obj.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    tmp = val_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(val, f, indent=2)
    os.replace(tmp, val_path)
    print(f"calibration rows: {len(cal)}, harmonized rows: {len(harm)}")


if __name__ == "__main__":
    main()