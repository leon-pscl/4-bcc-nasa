"""Reality check: monthly totals for the starter areas + k per tile.

Reads the partitioned datasets built by the pipeline
(`python -m firecal.ingest`, `python -m firecal.cells`, `python -m firecal.harmonize`).
"""

import argparse, os, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb

from firecal.config import Settings
from firecal.dataset import read_dataset
from firecal.harmonize.db import _metrics

AREAS = {
    "central_kalimantan": (110.7, -3.6, 115.9, 0.8),
    "northern_thailand": (97.3, 17.0, 101.5, 20.5),
    "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738),
    "rondonia": (-66.0, -13.7, -60.0, -7.9),
    "bolivia_east": (-64, -18, -60, -14),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="southeast_asia")
    ap.add_argument("--areas", nargs="*", default=list(AREAS))
    ap.add_argument("--calibration", default=None)
    args = ap.parse_args()
    settings = Settings.from_env()
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    h = read_dataset(settings, "harmonized_daily", [args.region])
    for name in args.areas:
        w, s, e, n = AREAS[name]
        sql = f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {h}
        WHERE cell_lat_idx * 0.05 + 0.025 BETWEEN {s} AND {n}
          AND cell_lon_idx * 0.05 + 0.025 BETWEEN {w} AND {e}
        GROUP BY 1,2 ORDER BY 1,2
        """
        rows = con.execute(sql).fetchall()
        by_year = {}
        for y, m, v in rows:
            by_year.setdefault(y, {})[m] = v
        print("=== " + name)
        for y in sorted(by_year):
            top = sorted(by_year[y].items(), key=lambda kv: -(kv[1] or 0))[:3]
            print(f"  {y}: top months {[(m, round(v)) for m, v in top]}")
        tot = {}
        for y, d in by_year.items():
            for m, v in d.items():
                tot[m] = tot.get(m, 0) + (v or 0)
        print("  season (sum over years, top 4 months):",
              [(m, round(v)) for m, v in sorted(tot.items(), key=lambda kv: -kv[1])[:4]])

    print("=== k per tile")
    cal_path = args.calibration
    if cal_path is None:
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    if not os.path.exists(cal_path):
        print("  (no calibration.parquet; run python -m firecal.harmonize)")
        return
    rows = con.execute(
        "SELECT tile_id, month, k, level, modis_celldays, viirs_celldays FROM read_parquet('"
        + cal_path + "') WHERE level='tile_month'").fetchall()
    per_tile = {}
    for t, m, k, lvl, a, v in rows:
        per_tile.setdefault(t, []).append((k, lvl, a, v))
    med = {t: statistics.median(x[0] for x in ks) for t, ks in per_tile.items()}
    print("  tiles:", len(per_tile))
    vals = list(med.values())
    print("  k median:", round(statistics.median(vals), 4),
          "min:", round(min(vals), 4), "max:", round(max(vals), 4))
    top = sorted(med.items(), key=lambda kv: -kv[1])[:15]
    print("  15 highest k tiles:")
    for t, k in top:
        a = max(x[2] for x in per_tile[t]); v = max(x[3] for x in per_tile[t])
        print(f"    {t}: k={k:.3f} aqua_cd={a} viirs_cd={v}")
    bottom = sorted(med.items(), key=lambda kv: kv[1])[:15]
    print("  15 lowest k tiles:")
    for t, k in bottom:
        a = max(x[2] for x in per_tile[t]); v = max(x[3] for x in per_tile[t])
        print(f"    {t}: k={k:.3f} aqua_cd={a} viirs_cd={v}")
    lv = con.execute("SELECT level, COUNT(*) FROM read_parquet('" + cal_path +
                     "') GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("  rows per level:", lv)
    rows_all = con.execute(
        "SELECT k, modis_celldays FROM read_parquet('" + cal_path +
        "') WHERE level='tile_month'").fetchall()
    vals_all = [r[0] for r in rows_all]
    print("  per tile-month k: min", round(min(vals_all), 4),
          "max", round(max(vals_all), 4),
          "| per-tile median range:", round(min(vals), 4), "-", round(max(vals), 4))
    small = [r for r in rows_all if r[1] < 30]
    print("  tile_month rows below MIN_CALIBRATION_CELLDAYS:", len(small))
    print("  their k range:", round(min(r[0] for r in small), 4) if small else None,
          "-", round(max(r[0] for r in small), 4) if small else None)
    area_validation(con, settings, args.region)


def area_validation(con, settings, region):
    """Held-out validation per starter area (Aqua x k vs SNPP cell-days)."""
    from firecal.harmonize.db import calibration_sql
    cd = read_dataset(settings, "celldays", [region])
    shrink = getattr(settings, "SHRINK_M", 0)
    cal = calibration_sql(cd, settings.CALIBRATION_YEARS,
                          settings.MIN_CALIBRATION_CELLDAYS, shrink)
    con.execute("CREATE OR REPLACE TEMP VIEW cd_v AS SELECT * FROM " + cd)
    con.execute("CREATE OR REPLACE TEMP VIEW cal_v AS " + cal)
    print("=== validation per starter area")
    for name, (w, s, e, n) in AREAS.items():
        sql = f"""
        WITH k AS (
          SELECT region, tile_id, month, k FROM cal_v
          QUALIFY ROW_NUMBER() OVER (PARTITION BY region, tile_id, month ORDER BY
            CASE level WHEN 'tile_month' THEN 1 WHEN 'tile' THEN 2
                       WHEN 'all_month' THEN 3 ELSE 4 END) = 1
        ),
        km AS (SELECT region, month, k FROM cal_v WHERE tile_id='ALL' AND month BETWEEN 1 AND 12),
        ka AS (SELECT region, k FROM cal_v WHERE tile_id='ALL' AND month=0),
        cd AS (
          SELECT region, platform, date_local, tile_id,
                 EXTRACT(month FROM date_local)::INTEGER AS month,
                 EXTRACT(year FROM date_local)::INTEGER AS year
          FROM cd_v
          WHERE cell_lat_idx * 0.05 + 0.025 BETWEEN {s} AND {n}
            AND cell_lon_idx * 0.05 + 0.025 BETWEEN {w} AND {e}
        ),
        snpp_dates AS (SELECT DISTINCT date_local FROM cd WHERE platform='SNPP'),
        aqua_dates AS (SELECT DISTINCT date_local FROM cd WHERE platform='Aqua'),
        outage AS (SELECT date_local FROM aqua_dates
                   WHERE date_local NOT IN (SELECT date_local FROM snpp_dates)),
        aqua_k AS (
          SELECT cd.year, cd.month, COUNT(*)::DOUBLE AS n,
                 COALESCE(k.k, km.k, ka.k) AS kv
          FROM cd
          LEFT JOIN k ON k.region=cd.region AND k.tile_id=cd.tile_id AND k.month=cd.month
          LEFT JOIN km ON km.region=cd.region AND km.month=cd.month
          LEFT JOIN ka ON ka.region=cd.region
          WHERE cd.platform='Aqua' AND cd.date_local NOT IN (SELECT date_local FROM outage)
          GROUP BY 1,2,4
        ),
        modis_m AS (SELECT year, month, COALESCE(SUM(n*kv), 0) AS monthly_modis FROM aqua_k GROUP BY 1,2),
        viirs_m AS (SELECT year, month, COUNT(*)::DOUBLE AS monthly_viirs
                    FROM cd WHERE platform='SNPP' GROUP BY 1,2)
        SELECT m.year, m.month, m.monthly_modis, v.monthly_viirs
        FROM modis_m m JOIN viirs_m v USING (year, month)
        """
        rows = con.execute(sql).fetchall()
        if not rows:
            print(f"  {name}: no data")
            continue
        for label, (y0, y1) in [("calibration", settings.CALIBRATION_YEARS),
                                ("held-out", settings.VALIDATION_YEARS)]:
            sub = [r for r in rows if y0 <= r[0] <= y1]
            m = _metrics([(r[3], r[2]) for r in sub])
            print(f"  {name} [{label}]: r={m['pearson_r']:.4f} "
                  f"bias={m['bias_pct']:.2f}% mape={m['median_abs_pct_error']:.2f}% "
                  f"months={len(sub)}")


if __name__ == "__main__":
    main()
