"""C16 backtest-lite: climatology skill per test year, 2015-2025.

For each test year Y and each target month (all 12), with climatology from
years before Y only:
- top-10% capture: share of the month's fire that fell in the 10% of kept
  cells with the highest climatology mean for that month;
- the Brier score of p_fire (mean over kept cells of (p - 1{value >= T})^2).
Pooled over all (Y, month) pairs and per year. No model is fit: this is the
climatology skill.
"""

import json
import os
from pathlib import Path

SERIES_START = 2003


def _kept_src(settings, region):
    p = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    return f"read_parquet('{p.as_posix()}') WHERE keep"


def _year_stats(con, settings, region, y):
    monthly_root = os.path.join(settings.DATA_PROCESSED, "monthly_cells").replace(os.sep, "/")
    p_first = max(SERIES_START, settings.OUTLOOK_PFIRE_START)
    nbr = settings.OUTLOOK_NBR
    bl = y - 1
    T = settings.OUTLOOK_FIRE_THRESHOLD
    con.execute("DROP TABLE IF EXISTS _bt_kept")
    con.execute(f"CREATE TEMP TABLE _bt_kept AS SELECT g_lat_idx, g_lon_idx FROM {_kept_src(settings, region)}")
    con.execute("DROP TABLE IF EXISTS _bt_hist")
    con.execute(f"""
    CREATE TEMP TABLE _bt_hist AS
    WITH cells AS (SELECT g_lat_idx, g_lon_idx, unnest(range(1, 13)) AS month FROM _bt_kept),
         years AS (SELECT unnest(range({SERIES_START}, {bl + 1})) AS year)
    SELECT c.g_lat_idx, c.g_lon_idx, c.month, y.year,
           COALESCE(mc.value, 0)::DOUBLE AS value
    FROM cells c CROSS JOIN years y
    LEFT JOIN read_parquet('{monthly_root}/region={region}/**/*.parquet') mc
      ON mc.g_lat_idx = c.g_lat_idx AND mc.g_lon_idx = c.g_lon_idx
     AND mc.month = c.month AND mc.year = y.year
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _bt_agg AS
    SELECT g_lat_idx, g_lon_idx, month,
           AVG(value) AS mean,
           SUM((value >= {T})::INT) FILTER (WHERE year >= {p_first})::DOUBLE AS fire_pfy,
           SUM(1) FILTER (WHERE year >= {p_first})::INT AS n_pfy
    FROM _bt_hist GROUP BY 1, 2, 3
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _bt_nbr AS
    SELECT a.g_lat_idx, a.g_lon_idx, a.month, AVG(b.fire_pfy / NULLIF(b.n_pfy, 0)) AS p_nbr
    FROM _bt_agg a JOIN _bt_agg b
      ON b.month = a.month AND ABS(b.g_lat_idx - a.g_lat_idx) <= {nbr} AND ABS(b.g_lon_idx - a.g_lon_idx) <= {nbr}
    GROUP BY 1, 2, 3
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _bt_clim AS
    SELECT a.g_lat_idx, a.g_lon_idx, a.month, a.mean,
           (a.fire_pfy + {settings.OUTLOOK_CLIM_SHRINK_M} * COALESCE(n.p_nbr, 0)) /
           (a.n_pfy + {settings.OUTLOOK_CLIM_SHRINK_M}) AS p_fire
    FROM _bt_agg a LEFT JOIN _bt_nbr n USING (g_lat_idx, g_lon_idx, month)
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _bt_act AS
    SELECT k.g_lat_idx, k.g_lon_idx, u.month, COALESCE(mc.value, 0)::DOUBLE AS actual
    FROM _bt_kept k CROSS JOIN (SELECT unnest(range(1, 13)) AS month) u
    LEFT JOIN read_parquet('{monthly_root}/region={region}/year={y}/*.parquet') mc
      ON mc.g_lat_idx = k.g_lat_idx AND mc.g_lon_idx = k.g_lon_idx AND mc.month = u.month
    """)
    con.execute("""
    CREATE OR REPLACE TEMP TABLE _bt_scored AS
    SELECT c.month, c.mean, c.p_fire, a.actual,
           QUANTILE_CONT(c.mean, 0.9) OVER (PARTITION BY c.month) AS q90
    FROM _bt_clim c JOIN _bt_act a USING (g_lat_idx, g_lon_idx, month)
    """)
    month_rows = con.execute(f"""
    SELECT month,
           SUM(CASE WHEN mean >= q90 THEN actual ELSE 0 END) AS top_fire,
           SUM(actual) AS total_fire,
           AVG(POWER(p_fire - (actual >= {T})::INT, 2)) AS brier,
           COUNT(*) AS n_cells
    FROM _bt_scored GROUP BY month ORDER BY month
    """).fetchall()
    totals = con.execute(f"""
    SELECT SUM(CASE WHEN mean >= q90 THEN actual ELSE 0 END), SUM(actual),
           SUM(POWER(p_fire - (actual >= {T})::INT, 2)), COUNT(*)
    FROM _bt_scored
    """).fetchone()
    for t in ("_bt_kept", "_bt_hist", "_bt_agg", "_bt_nbr", "_bt_clim", "_bt_act", "_bt_scored"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    return month_rows, totals


def build_backtest(settings, region, test_years=None, dry_run=False):
    from firecal.duck import connect
    grid_path = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    if not grid_path.exists():
        raise FileNotFoundError(f"C11 not built yet: {grid_path}")
    t0 = test_years or list(range(settings.OUTLOOK_TEST_YEARS[0], settings.OUTLOOK_TEST_YEARS[1] + 1))
    con = connect(settings, "pipeline")
    per_year = {}
    pool = [0.0, 0.0, 0.0, 0]  # top_fire, total_fire, brier_sum, n
    try:
        for y in t0:
            rows, totals = _year_stats(con, settings, region, y)
            top_fire, total_fire, brier_sum, n = (totals[0] or 0.0, totals[1] or 0.0,
                                                  totals[2] or 0.0, totals[3] or 0)
            pool[0] += top_fire
            pool[1] += total_fire
            pool[2] += brier_sum
            pool[3] += n
            per_year[y] = {
                "top10_capture_pct": round(100 * top_fire / total_fire, 2) if total_fire else None,
                "brier": round(brier_sum / n, 4) if n else None,
                "fire": round(total_fire, 1),
                "months": {str(int(m)): {"capture_pct": round(100 * t / tf, 2) if tf else None,
                                          "brier": round(b, 4),
                                          "fire": round(tf, 1)} for m, t, tf, b, _ in rows},
            }
            print(f"backtest {y}: capture {per_year[y]['top10_capture_pct']}%  "
                  f"brier {per_year[y]['brier']}  fire {per_year[y]['fire']}")
    finally:
        con.close()
    pooled = {
        "top10_capture_pct": round(100 * pool[0] / pool[1], 2) if pool[1] else None,
        "brier": round(pool[2] / pool[3], 4) if pool[3] else None,
        "fire": round(pool[1], 1),
    }
    result = {
        "region": region,
        "test_years": list(t0),
        "big_years": [y for y in (2015, 2019, 2023) if y in t0],
        "baseline_rule": (f"years before the test year only; means from {SERIES_START}, "
                          f"p_fire from max({SERIES_START}, {settings.OUTLOOK_PFIRE_START}); "
                          f"T = {settings.OUTLOOK_FIRE_THRESHOLD}; kept cells only"),
        "pooled": pooled,
        "per_year": {str(y): per_year[y] for y in t0},
    }
    if dry_run:
        return result
    out_dir = Path(settings.DATA_PROCESSED) / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"outlook_{region}.json"
    tmp = str(out) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    os.replace(tmp, out)
    return result
