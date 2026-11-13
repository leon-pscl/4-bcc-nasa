"""Calibrate NOAA-20 and NOAA-21 against S-NPP (C3 rows with platform/reference).

k_platform = SNPP cell-days / platform cell-days, per tile x month, over the
overlap years of the two platforms.
"""

import argparse, os, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb

from firecal.config import Settings
from firecal.dataset import read_dataset
from firecal.harmonize.db import _metrics

OVERLAP = {
    "NOAA20": (2018, 2025),   # calibration 2018-2023, validation 2024-2025
    "NOAA21": (2023, 2026),   # calibration 2023-2024, validation 2025-2026
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="southeast_asia")
    ap.add_argument("--min-celldays", type=int, default=30)
    args = ap.parse_args()
    settings = Settings.from_env()
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    cd = read_dataset(settings, "celldays", [args.region])
    con.execute("CREATE OR REPLACE TEMP VIEW cd_v AS SELECT * FROM " + cd)

    for platform, (y0, y1) in OVERLAP.items():
        cal_y = (y0, y1 - 2) if y1 - 2 >= y0 else (y0, y0)
        val_y = (y1 - 1, y1)
        print(f"=== {platform} vs SNPP (calibration {cal_y}, validation {val_y})")
        sql = f"""
        WITH m AS (
          SELECT tile_id, EXTRACT(month FROM date_local)::INTEGER AS month,
                 SUM(CASE WHEN platform='SNPP' THEN n_detections ELSE 0 END) AS snpp,
                 SUM(CASE WHEN platform='{platform}' THEN n_detections ELSE 0 END) AS plat
          FROM cd_v
          WHERE year(date_local) BETWEEN {cal_y[0]} AND {cal_y[1]}
            AND platform IN ('SNPP','{platform}')
          GROUP BY 1,2
        )
        SELECT tile_id, month, snpp, plat,
               CASE WHEN plat >= {args.min_celldays} THEN snpp::DOUBLE/plat ELSE NULL END AS k
        FROM m WHERE plat > 0
        """
        rows = con.execute(sql).fetchall()
        ks = [r[4] for r in rows if r[4] is not None]
        if not ks:
            print("  not enough overlap data")
            continue
        print(f"  tiles x months with data: {len(ks)}, "
              f"k median {statistics.median(ks):.3f}, range {min(ks):.3f}-{max(ks):.3f}")
        # validation: monthly totals platform x k vs SNPP
        v_sql = f"""
        WITH m AS (
          SELECT year(date_local)::INTEGER AS year,
                 EXTRACT(month FROM date_local)::INTEGER AS month,
                 SUM(CASE WHEN platform='SNPP' THEN n_detections ELSE 0 END) AS snpp,
                 SUM(CASE WHEN platform='{platform}' THEN n_detections ELSE 0 END) AS plat
          FROM cd_v
          WHERE year(date_local) BETWEEN {val_y[0]} AND {val_y[1]}
            AND platform IN ('SNPP','{platform}')
          GROUP BY 1,2
        )
        SELECT year, month, snpp, plat FROM m WHERE snpp > 0 AND plat > 0 ORDER BY 1,2
        """
        vrows = con.execute(v_sql).fetchall()
        pairs = [(r[2], r[3] * statistics.median(ks)) for r in vrows]
        met = _metrics(pairs)
        print(f"  validation ({val_y[0]}-{val_y[1]}): r={met['pearson_r']:.4f} "
              f"bias={met['bias_pct']:.2f}% mape={met['median_abs_pct_error']:.2f}% "
              f"months={len(pairs)}")
        # same-year comparison (all overlap years)
        a_sql = f"""
        WITH m AS (
          SELECT year(date_local)::INTEGER AS year,
                 EXTRACT(month FROM date_local)::INTEGER AS month,
                 SUM(CASE WHEN platform='SNPP' THEN n_detections ELSE 0 END) AS snpp,
                 SUM(CASE WHEN platform='{platform}' THEN n_detections ELSE 0 END) AS plat
          FROM cd_v
          WHERE platform IN ('SNPP','{platform}')
          GROUP BY 1,2
        )
        SELECT year, month, snpp, plat FROM m WHERE snpp > 0 AND plat > 0 ORDER BY 1,2
        """
        arows = con.execute(a_sql).fetchall()
        apairs = [(r[2], r[3] * statistics.median(ks)) for r in arows]
        amet = _metrics(apairs)
        print(f"  all overlap years: r={amet['pearson_r']:.4f} bias={amet['bias_pct']:.2f}% "
              f"mape={amet['median_abs_pct_error']:.2f}% months={len(apairs)}")


if __name__ == "__main__":
    main()
