"""CLI for firecal.harmonize: rebuild calibration + harmonized partitions."""

import argparse
import json
import os
import sys
import time

from firecal.config import Settings
from firecal.dataset import CELLDAYS, DETECTIONS, HARMONIZED, write_data_versions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--out-validation", default=None)
    args = parser.parse_args()
    settings = Settings.from_env()

    from firecal.harmonize.db import rebuild
    t0 = time.time()
    rebuilt = rebuild(settings, region=args.region)
    print(f"rebuilt {len(rebuilt)} harmonized partitions in {time.time() - t0:.1f}s")

    if args.region:
        import duckdb
        from firecal.dataset import read_dataset
        from firecal.harmonize.db import (build_validation, calibration_all_sql,
                                          calibration_sql)
        con = duckdb.connect()
        con.execute("PRAGMA threads=4")
        cd = read_dataset(settings, CELLDAYS, [args.region])
        cal = calibration_sql(cd, settings.CALIBRATION_YEARS, settings.MIN_CALIBRATION_CELLDAYS)
        con.execute("CREATE OR REPLACE TEMP VIEW cal_raw AS " + cal)
        con.execute("CREATE OR REPLACE TEMP VIEW cal_all AS "
                    + calibration_all_sql("cal_raw", settings.MIN_CALIBRATION_CELLDAYS))
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        con.execute(
            "COPY (SELECT region, tile_id, CAST(month AS SMALLINT) AS month, k, "
            "CAST(modis_celldays AS BIGINT) AS modis_celldays, "
            "CAST(viirs_celldays AS BIGINT) AS viirs_celldays, level "
            "FROM (SELECT * FROM cal_raw UNION ALL SELECT * FROM cal_all)) "
            f"TO '{cal_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        val = build_validation(con, cd, cal, args.region,
                               settings.CALIBRATION_YEARS, settings.VALIDATION_YEARS)
        out = args.out_validation or os.path.join(settings.DATA_PROCESSED, "validation.json")
        with open(out, "w") as f:
            json.dump(val, f, indent=2)
        print("calibration r", val["calibration_years"]["metrics"]["pearson_r"],
              "bias", val["calibration_years"]["metrics"]["bias_pct"])
        print("validation r", val["validation_years"]["metrics"]["pearson_r"],
              "bias", val["validation_years"]["metrics"]["bias_pct"])
    write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])


if __name__ == "__main__":
    main()
