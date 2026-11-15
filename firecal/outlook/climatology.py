"""C13 climatology: per kept cell and calendar month.

Baseline: complete years before the target year, first year = 2003. p_fire uses
years from OUTLOOK_PFIRE_START (2013, VIIRS-only); mean/median/p25/p75 and
expected use the full record. p_fire = (n_fire_years + m * p_nbr) / (n_years + m)
with m = OUTLOOK_CLIM_SHRINK_M (3), p_nbr the mean raw fire-share of the
(2*NBR+1)^2 neighbourhood of kept cells (including the cell itself), kept
cells only. No look-ahead: climatology for a target in year Y never reads
year Y or later.
"""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from firecal.dataset import fingerprint

SERIES_START = 2003


def complete_baseline_last(settings, latest_date):
    """Last complete year on or before latest_date (a year is complete at Dec 31)."""
    y, m, d = (int(p) for p in latest_date.split("-"))
    return y if (m == 12 and d == 31) else y - 1


def _connect(settings):
    from firecal.duck import connect
    return connect(settings, "pipeline")


def _month_list():
    return list(range(1, 13))


def _climatology_frame(settings, region, baseline_first, baseline_last, path):
    from firecal.outlook.grid import g_center
    con = _connect(settings)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        kept_src = _kept_src(settings, region)
        monthly_root = os.path.join(settings.DATA_PROCESSED, "monthly_cells").replace(os.sep, "/")
        p_first = max(baseline_first, settings.OUTLOOK_PFIRE_START)
        nbr = settings.OUTLOOK_NBR
        con.execute("DROP TABLE IF EXISTS _clim_years")
        con.execute(f"CREATE TEMP TABLE _clim_years AS SELECT unnest(range({baseline_first}, {baseline_last + 1})) AS year")
        con.execute("DROP TABLE IF EXISTS _pfy_years")
        con.execute(f"CREATE TEMP TABLE _pfy_years AS SELECT unnest(range({p_first}, {baseline_last + 1})) AS year")
        con.execute("DROP TABLE IF EXISTS _kept")
        con.execute(f"CREATE TEMP TABLE _kept AS SELECT g_lat_idx, g_lon_idx FROM {kept_src}")
        con.execute("DROP TABLE IF EXISTS _m")
        con.execute(f"CREATE TEMP TABLE _m AS SELECT unnest(range(1, 13)) AS month")
        # full zero-filled baseline grid
        con.execute("""
        CREATE TEMP TABLE _grid AS
        SELECT k.g_lat_idx, k.g_lon_idx, m.month, y.year
        FROM _kept k CROSS JOIN _m m CROSS JOIN _clim_years y
        """)
        con.execute(f"""
        CREATE TEMP TABLE _joined AS
        SELECT g.g_lat_idx, g.g_lon_idx, g.month, g.year,
               COALESCE(mc.value, 0)::DOUBLE AS value
        FROM _grid g
        LEFT JOIN read_parquet('{monthly_root}/region={region}/**/*.parquet') mc
          ON mc.g_lat_idx = g.g_lat_idx AND mc.g_lon_idx = g.g_lon_idx
         AND mc.month = g.month AND mc.year = g.year
        """)
        # raw VIIRS-years share per cell-month (unshrunk), for the neighbourhood prior
        con.execute(f"""
        CREATE TEMP TABLE _raw AS
        SELECT g_lat_idx, g_lon_idx, month,
               AVG((value >= {settings.OUTLOOK_FIRE_THRESHOLD})::INT)::DOUBLE AS p_raw
        FROM _joined WHERE year >= {p_first} GROUP BY 1, 2, 3
        """)
        # neighbourhood mean of p_raw over kept cells (incl. self), 5x5 for NBR=2
        con.execute(f"""
        CREATE TEMP TABLE _nbr AS
        SELECT a.g_lat_idx, a.g_lon_idx, a.month, AVG(b.p_raw) AS p_nbr
        FROM _raw a JOIN _raw b
          ON b.month = a.month
         AND ABS(b.g_lat_idx - a.g_lat_idx) <= {nbr}
         AND ABS(b.g_lon_idx - a.g_lon_idx) <= {nbr}
        GROUP BY 1, 2, 3
        """)
        con.execute(f"""
        CREATE TEMP TABLE _agg AS
        SELECT j.g_lat_idx, j.g_lon_idx, j.month,
               COUNT(*) AS n_years,
               SUM(j.value) AS total,
               AVG(j.value) AS mean,
               MEDIAN(j.value) AS median,
               quantile_cont(j.value, 0.25) AS p25,
               quantile_cont(j.value, 0.75) AS p75,
               SUM((j.value >= {settings.OUTLOOK_FIRE_THRESHOLD})::INT) AS fire_years_all,
               SUM(CASE WHEN j.year >= {p_first} THEN (j.value >= {settings.OUTLOOK_FIRE_THRESHOLD})::INT ELSE 0 END) AS fire_years_pfy,
               SUM(CASE WHEN j.year >= {p_first} THEN 1 ELSE 0 END) AS n_pfy
        FROM _joined j GROUP BY 1, 2, 3
        """)
        con.execute(f"""
        CREATE TEMP TABLE _out AS
        SELECT a.g_lat_idx, a.g_lon_idx, a.month,
               {baseline_first}::SMALLINT AS baseline_first, {baseline_last}::SMALLINT AS baseline_last,
               a.n_years::SMALLINT AS n_years,
               (a.fire_years_pfy + {settings.OUTLOOK_CLIM_SHRINK_M} * COALESCE(n.p_nbr, 0)) /
               (a.n_pfy + {settings.OUTLOOK_CLIM_SHRINK_M}) AS p_fire,
               a.mean, a.median, a.p25, a.p75
        FROM _agg a LEFT JOIN _nbr n
          ON n.g_lat_idx = a.g_lat_idx AND n.g_lon_idx = a.g_lon_idx AND n.month = a.month
        """)
        # rank of mean within the cell's 12 months (1 = highest mean)
        con.execute("""
        CREATE TEMP TABLE _ranked AS
        SELECT *, RANK() OVER (PARTITION BY g_lat_idx, g_lon_idx ORDER BY mean DESC)::TINYINT AS rank_in_year
        FROM _out
        """)
        con.execute(f"""
        COPY _ranked TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        # region tag: add it in a second pass to keep the copy simple
        con.execute(f"""
        CREATE OR REPLACE TABLE climatology AS SELECT '{region}' AS region, * FROM read_parquet('{path}')
        """)
        con.execute(f"COPY climatology TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        for t in ("_grid", "_joined", "_raw", "_nbr", "_agg", "_out", "_ranked", "_clim_years", "_pfy_years", "_kept", "_m"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
    finally:
        con.close()


def _kept_src(settings, region):
    p = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    return f"read_parquet('{p.as_posix()}') WHERE keep"


def build_climatology(settings, region, latest_date, dry_run=False):
    baseline_first = SERIES_START
    baseline_last = complete_baseline_last(settings, latest_date)
    if baseline_last < baseline_first:
        raise ValueError(f"no complete baseline year before {latest_date}")
    path = Path(settings.DATA_PROCESSED) / "climatology" / f"region={region}" / "part-0.parquet"
    tmp = str(path) + ".tmp.parquet"
    _climatology_frame(settings, region, baseline_first, baseline_last, tmp)
    df = pd.read_parquet(tmp)
    n = len(df)
    print(f"climatology: {n} rows (kept cells x 12 months), baseline {baseline_first}-{baseline_last}")
    if dry_run:
        os.unlink(tmp)
        return df
    from firecal.contracts import validate_climatology
    out = df[["region", "g_lat_idx", "g_lon_idx", "month", "baseline_first", "baseline_last",
              "n_years", "p_fire", "mean", "median", "p25", "p75", "rank_in_year"]]
    out = out.astype({"g_lat_idx": "int32", "g_lon_idx": "int32", "month": "int8",
                      "baseline_first": "int16", "baseline_last": "int16", "n_years": "int16",
                      "rank_in_year": "int8"})
    validate_climatology(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
    os.unlink(tmp)
    return out
