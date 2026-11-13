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
        from firecal.harmonize.db import build_validation, monthly_sql
        con = duckdb.connect()
        con.execute("PRAGMA threads=4")
        cd = read_dataset(settings, CELLDAYS, [args.region])
        from firecal.harmonize.db import calibration_sql
        shrink = getattr(settings, "SHRINK_M", 0)
        cal = calibration_sql(cd, settings.CALIBRATION_YEARS,
                              settings.MIN_CALIBRATION_CELLDAYS, shrink)
        val = build_validation(con, cd, cal, args.region,
                               settings.CALIBRATION_YEARS, settings.VALIDATION_YEARS)
        out = args.out_validation or os.path.join(settings.DATA_PROCESSED, "validation.json")
        with open(out, "w") as f:
            json.dump(val, f, indent=2)
        print("calibration r", val["calibration_years"]["metrics"]["pearson_r"],
              "bias", val["calibration_years"]["metrics"]["bias_pct"])
        print("validation r", val["validation_years"]["metrics"]["pearson_r"],
              "bias", val["validation_years"]["metrics"]["bias_pct"])
        # coverage.json: latest_date is the last day of the harmonized series
        h_root = os.path.join(settings.DATA_PROCESSED, HARMONIZED)
        if os.path.exists(h_root):
            import duckdb as _duck
            vcon = _duck.connect()
            stats = vcon.execute(
                "SELECT MIN(date_local), MAX(date_local) FROM read_parquet('" +
                h_root.replace(os.sep, '/') + "/region=" + args.region + "/*/*.parquet')"
            ).fetchone()
            latest = str(stats[1])
            start = str(stats[0])
            reg_path = os.path.join("config", "regions.json")
            meta = {}
            if os.path.exists(reg_path):
                meta = next((r for r in __import__("json").load(open(reg_path))["regions"]
                             if r["name"] == args.region), {})
            bbox = settings.REGIONS.get(args.region) or tuple(meta.get("bbox", [0, 0, 0, 0]))
            cov_path = os.path.join(settings.DATA_PROCESSED, "coverage.json")
            cov = []
            if os.path.exists(cov_path):
                try:
                    cov = json.load(open(cov_path))
                except Exception:
                    cov = []
            entry = {"name": args.region, "label": meta.get("label", args.region),
                     "bbox": list(bbox), "countries": meta.get("countries", []),
                     "start": start, "end": latest,
                     "platforms": ["Aqua", "SNPP", "NOAA20", "NOAA21"],
                     "latest_date": latest, "synthetic": False}
            out_cov = [e for e in cov if e.get("name") != args.region] + [entry]
            tmp = cov_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(out_cov, f, indent=2)
            os.replace(tmp, cov_path)
            print("latest_date:", latest)
    write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])


if __name__ == "__main__":
    main()
