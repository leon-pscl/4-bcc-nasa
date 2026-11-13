"""DuckDB harmonization (C3 calibration, C4 harmonized daily, C5 validation).

All the work is SQL: calibration factors per tile x month, the harmonized daily
series and the validation metrics. Output is Hive-partitioned by (region, year).
"""

import json
import math
import os

import duckdb

from firecal.dataset import fingerprint, read_dataset, write_partition


def base_counts_sql(cd, cal_years, platform="Aqua", reference="SNPP"):
    return f"""
    SELECT region, tile_id, EXTRACT(month FROM date_local)::INTEGER AS month, platform,
           COUNT(*) AS n
    FROM {cd}
    WHERE year(date_local) BETWEEN {cal_years[0]} AND {cal_years[1]}
      AND platform IN ('{platform}','{reference}')
    GROUP BY 1,2,3,4
    """


def calibration_sql(cd, cal_years, min_cal, shrink_m=0, platform="Aqua", reference="SNPP"):
    """C3: k = SNPP cell-days / Aqua cell-days per tile x month, with shrinkage.

    Each tile x month factor is shrunk toward its tile's factor, and the tile
    factor is shrunk toward the region factor:

        k_month = (viirs_month + m * k_tile) / (aqua_month + m)
        k_tile  = (viirs_tile  + m * k_region) / (aqua_tile  + m)
    """
    return f"""
    WITH c AS ({base_counts_sql(cd, cal_years, platform, reference)}),
    a AS (SELECT tile_id, month, region, SUM(n) AS aqua FROM c WHERE platform='{platform}' GROUP BY 1,2,3),
    s AS (SELECT tile_id, month, region, SUM(n) AS viirs FROM c WHERE platform='{reference}' GROUP BY 1,2,3),
    m AS (
      SELECT COALESCE(a.tile_id,s.tile_id) AS tile_id, COALESCE(a.month,s.month) AS month,
             a.region, COALESCE(a.aqua,0) AS aqua, COALESCE(s.viirs,0) AS viirs
      FROM a FULL OUTER JOIN s
        ON a.tile_id=s.tile_id AND a.month=s.month AND a.region=s.region
    ),
    tile_tot AS (SELECT tile_id, region, SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m GROUP BY 1,2),
    month_tot AS (SELECT month, region, SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m GROUP BY 1,2),
    all_tot AS (SELECT region, SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m GROUP BY 1),
    base AS (
      SELECT m.region, m.tile_id, m.month, m.aqua, m.viirs,
             COALESCE(tt.aqua,0) AS t_aqua, COALESCE(tt.viirs,0) AS t_viirs,
             COALESCE(mt.aqua,0) AS m_aqua, COALESCE(mt.viirs,0) AS m_viirs,
             COALESCE(gt.aqua,0) AS g_aqua, COALESCE(gt.viirs,0) AS g_viirs,
             COALESCE(gt.aqua,0) AS r_aqua, COALESCE(gt.viirs,0) AS r_viirs
      FROM m
      LEFT JOIN tile_tot tt ON tt.tile_id=m.tile_id AND tt.region=m.region
      LEFT JOIN month_tot mt ON mt.month=m.month AND mt.region=m.region
      LEFT JOIN all_tot gt ON gt.region=m.region
    ),
    shrunk AS (
      SELECT region, tile_id, month, aqua, viirs, t_aqua, t_viirs, m_aqua, m_viirs,
             g_aqua, g_viirs, r_aqua, r_viirs,
             r_viirs::DOUBLE / NULLIF(r_aqua, 0) AS region_k,
             (t_viirs + {shrink_m} * (r_viirs::DOUBLE / NULLIF(r_aqua, 0)))
               / NULLIF(t_aqua + {shrink_m}, 0) AS tile_k
      FROM base
    )
    SELECT region, CAST('{platform}' AS VARCHAR) AS platform,
           CAST('{reference}' AS VARCHAR) AS reference,
           tile_id, month,
      CASE WHEN aqua > 0 THEN (viirs + {shrink_m} * tile_k) / (aqua + {shrink_m})
           ELSE tile_k END AS k,
      CASE WHEN aqua >= {min_cal} THEN aqua
           WHEN t_aqua >= {min_cal} THEN t_aqua
           WHEN m_aqua >= {min_cal} THEN m_aqua
           ELSE g_aqua END AS modis_celldays,
      CASE WHEN aqua >= {min_cal} THEN viirs
           WHEN t_aqua >= {min_cal} THEN t_viirs
           WHEN m_aqua >= {min_cal} THEN m_viirs
           ELSE g_viirs END AS viirs_celldays,
      CASE WHEN aqua >= {min_cal} THEN 'tile_month'
           WHEN t_aqua >= {min_cal} THEN 'tile'
           WHEN m_aqua >= {min_cal} THEN 'all_month'
           ELSE 'all' END AS level
    FROM shrunk
    """


def calibration_all_sql(cal_rel, min_cal, shrink_m=0, platform="Aqua", reference="SNPP"):
    """The 'ALL' fallback rows: months 1-12 (all_month) and month 0 (all),
    shrunk toward the region factor."""
    return f"""
    WITH t AS (SELECT * FROM {cal_rel}),
    region_tot AS (SELECT region, SUM(modis_celldays) AS aqua, SUM(viirs_celldays) AS viirs
                   FROM t GROUP BY 1),
    month_tot AS (SELECT region, month, SUM(modis_celldays) AS aqua,
                         SUM(viirs_celldays) AS viirs
                  FROM t GROUP BY 1,2)
    SELECT region, CAST('{platform}' AS VARCHAR) AS platform,
           CAST('{reference}' AS VARCHAR) AS reference,
           'ALL' AS tile_id, month,
      CASE WHEN month = 0 THEN viirs::DOUBLE / NULLIF(aqua, 0)
           ELSE (viirs + {shrink_m} * (viirs::DOUBLE / NULLIF(aqua, 0)))
                  / NULLIF(aqua + {shrink_m}, 0) END AS k,
      aqua AS modis_celldays, viirs AS viirs_celldays,
      CASE WHEN aqua >= {min_cal} THEN 'all_month' ELSE 'all' END AS level
    FROM (
      SELECT region, month, aqua, viirs FROM month_tot
      UNION ALL
      SELECT region, 0, aqua, viirs FROM region_tot
    ) AS u
    """


def harmonized_sql(cd, cal_rel, series_start, switch_date):
    """C4: harmonized daily series per cell (no sensor/platform).

    Continuity: after SWITCH_DATE, SNPP cell-days are used where SNPP has data;
    else NOAA-20 x k(NOAA-20 -> SNPP); else NOAA-21 x k(NOAA-21 -> SNPP); else
    Aqua x k as a gap fill.
    """
    return f"""
    WITH cd AS (
      SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local, platform,
             EXTRACT(month FROM date_local)::INTEGER AS month
      FROM {cd} WHERE date_local >= DATE '{series_start}'
    ),
    k AS (
      SELECT region, platform, reference, tile_id, month, k FROM {cal_rel}
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, tile_id, month
                                 ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                     WHEN 'tile' THEN 2
                                                     WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    k_all_month AS (
      SELECT region, platform, reference, month, k FROM {cal_rel}
      WHERE tile_id = 'ALL' AND month BETWEEN 1 AND 12
    ),
    k_all AS (SELECT region, platform, reference, k FROM {cal_rel} WHERE tile_id = 'ALL' AND month = 0),
    aqua AS (
      SELECT cd.*, COALESCE(km.k, km_m.k, ka.k) AS k
      FROM cd
      LEFT JOIN k km ON km.region=cd.region AND km.platform='Aqua' AND km.reference='SNPP'
                     AND km.tile_id=cd.tile_id AND km.month=cd.month
      LEFT JOIN k_all_month km_m ON km_m.region=cd.region AND km_m.platform='Aqua'
                                 AND km_m.reference='SNPP' AND km_m.month=cd.month
      LEFT JOIN k_all ka ON ka.region=cd.region AND ka.platform='Aqua' AND ka.reference='SNPP'
      WHERE cd.platform = 'Aqua'
    ),
    n20 AS (
      SELECT cd.*, COALESCE(km.k, km_m.k, ka.k) AS k
      FROM cd
      LEFT JOIN k km ON km.region=cd.region AND km.platform='NOAA20' AND km.reference='SNPP'
                     AND km.tile_id=cd.tile_id AND km.month=cd.month
      LEFT JOIN k_all_month km_m ON km_m.region=cd.region AND km_m.platform='NOAA20'
                                 AND km_m.reference='SNPP' AND km_m.month=cd.month
      LEFT JOIN k_all ka ON ka.region=cd.region AND ka.platform='NOAA20' AND ka.reference='SNPP'
      WHERE cd.platform = 'NOAA20'
    ),
    n21 AS (
      SELECT cd.*, COALESCE(km.k, km_m.k, ka.k) AS k
      FROM cd
      LEFT JOIN k km ON km.region=cd.region AND km.platform='NOAA21' AND km.reference='SNPP'
                     AND km.tile_id=cd.tile_id AND km.month=cd.month
      LEFT JOIN k_all_month km_m ON km_m.region=cd.region AND km_m.platform='NOAA21'
                                 AND km_m.reference='SNPP' AND km_m.month=cd.month
      LEFT JOIN k_all ka ON ka.region=cd.region AND ka.platform='NOAA21' AND ka.reference='SNPP'
      WHERE cd.platform = 'NOAA21'
    ),
    snpp AS (SELECT * FROM cd WHERE platform = 'SNPP'),
    snpp_dates AS (SELECT DISTINCT region, date_local FROM snpp),
    n20_dates AS (SELECT DISTINCT region, date_local FROM n20),
    n21_dates AS (SELECT DISTINCT region, date_local FROM n21),
    aqua_dates AS (SELECT DISTINCT region, date_local FROM aqua),
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           k AS value, 'modis_scaled' AS basis
      FROM aqua WHERE date_local < DATE '{switch_date}'
    UNION ALL
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           1.0 AS value, 'viirs' AS basis
      FROM snpp WHERE date_local >= DATE '{switch_date}'
    UNION ALL
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           k AS value, 'viirs_noaa20' AS basis
      FROM n20 WHERE date_local >= DATE '{switch_date}'
        AND (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates)
    UNION ALL
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           k AS value, 'viirs_noaa21' AS basis
      FROM n21 WHERE date_local >= DATE '{switch_date}'
        AND (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates)
        AND (region, date_local) NOT IN (SELECT region, date_local FROM n20_dates)
    UNION ALL
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           k AS value, 'modis_gapfill' AS basis
      FROM aqua WHERE date_local >= DATE '{switch_date}'
        AND (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates)
        AND (region, date_local) NOT IN (SELECT region, date_local FROM n20_dates)
        AND (region, date_local) NOT IN (SELECT region, date_local FROM n21_dates)
    """


def monthly_sql(cd, cal_rel, series_start):
    """Monthly MODIS (Aqua x k) and VIIRS (S-NPP) totals, outage days excluded."""
    return f"""
    WITH cd AS (
      SELECT region, platform, date_local, tile_id,
             EXTRACT(month FROM date_local)::INTEGER AS month,
             EXTRACT(year FROM date_local)::INTEGER AS year
      FROM {cd} WHERE date_local >= DATE '{series_start}'
    ),
    k AS (
      SELECT region, platform, reference, tile_id, month, k FROM {cal_rel}
      WHERE platform='Aqua' AND reference='SNPP'
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, tile_id, month
                                 ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                     WHEN 'tile' THEN 2
                                                     WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    k_all_month AS (
      SELECT region, platform, reference, month, k FROM {cal_rel}
      WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month BETWEEN 1 AND 12
    ),
    k_all AS (SELECT region, platform, reference, k FROM {cal_rel}
              WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month=0),
    snpp_dates AS (SELECT DISTINCT region, date_local FROM cd WHERE platform='SNPP'),
    aqua_dates AS (SELECT DISTINCT region, date_local FROM cd WHERE platform='Aqua'),
    outage AS (SELECT region, date_local FROM aqua_dates
               WHERE (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates)),
    aqua_k AS (
      SELECT cd.region, cd.year, cd.month, cd.tile_id, COUNT(*)::DOUBLE AS n,
             COALESCE(k.k, km.k, ka.k) AS kv
      FROM cd
      LEFT JOIN k ON k.region=cd.region AND k.tile_id=cd.tile_id AND k.month=cd.month
      LEFT JOIN k_all_month km ON km.region=cd.region AND km.month=cd.month
      LEFT JOIN k_all ka ON ka.region=cd.region
      WHERE cd.platform='Aqua' AND (cd.region, cd.date_local) NOT IN (SELECT region, date_local FROM outage)
      GROUP BY 1,2,3,4,6
    ),
    modis_m AS (SELECT region, year, month, SUM(n*kv) AS monthly_modis FROM aqua_k GROUP BY 1,2,3),
    viirs_m AS (SELECT region, year, month, COUNT(*)::DOUBLE AS monthly_viirs
                FROM cd WHERE platform='SNPP' GROUP BY 1,2,3)
    SELECT m.region, m.year, m.month, m.monthly_modis, v.monthly_viirs
    FROM modis_m m JOIN viirs_m v USING (region, year, month)
    ORDER BY m.region, m.year, m.month
    """


def _metrics(pairs):
    """pairs: list of (viirs, modis). Returns pearson_r, bias_pct, median_abs_pct_error."""
    sel = [(v, m) for (v, m) in pairs if v >= 10]
    if len(sel) < 2:
        return {"pearson_r": 0.0, "bias_pct": 0.0, "median_abs_pct_error": 0.0}
    n = len(sel)
    mv = sum(v for v, _ in sel) / n
    mm = sum(m for _, m in sel) / n
    cov = sum((v - mv) * (m - mm) for v, m in sel) / n
    sv = math.sqrt(sum((v - mv) ** 2 for v, _ in sel) / n)
    sm = math.sqrt(sum((m - mm) ** 2 for _, m in sel) / n)
    r = cov / (sv * sm) if sv and sm else 0.0
    bias = (mm - mv) / mv * 100 if mv else 0.0
    errs = sorted(abs((m - v) / (v if v else 1)) * 100 for v, m in sel)
    return {"pearson_r": r, "bias_pct": bias, "median_abs_pct_error": errs[len(errs) // 2]}


def build_validation(con, cd_sql, cal_sql, region, cal_years, val_years):
    """C5 shape, per frontend-tasks.md 5.7."""
    con.execute("CREATE OR REPLACE TEMP VIEW cd_val AS SELECT * FROM " + cd_sql)
    con.execute("CREATE OR REPLACE TEMP VIEW cal_val AS " + cal_sql)
    rows = con.execute(monthly_sql("cd_val", "cal_val", "2003-01-01")).fetchall()
    rows = [r for r in rows if r[0] == region]

    def block(y0, y1):
        sub = [r for r in rows if y0 <= r[1] <= y1]
        per_year = {}
        for y in range(y0, y1 + 1):
            ys = [r for r in sub if r[1] == y]
            m = _metrics([(r[4], r[3]) for r in ys])
            m["monthly_viirs"] = [r[4] for r in ys]
            m["monthly_modis"] = [r[3] for r in ys]
            per_year[str(y)] = m
        agg = _metrics([(r[4], r[3]) for r in sub])
        agg["monthly_viirs"] = [r[4] for r in sub]
        agg["monthly_modis"] = [r[3] for r in sub]
        return {"years": list(range(y0, y1 + 1)), "metrics": agg, "per_year": per_year}

    return {"calibration_years": block(*cal_years), "validation_years": block(*val_years)}


def fit_calibration(celldays, settings, shrink_m=None):
    """DataFrame in -> calibration DataFrame out (small inputs / tests)."""
    import pandas as pd
    from firecal.contracts import validate_calibration

    shrink_m = getattr(settings, "SHRINK_M", 0) if shrink_m is None else shrink_m
    df = celldays.copy()
    if "region" not in df.columns:
        df["region"] = "test"
    if not len(df):
        raise ValueError("no calibration years present in data")
    con = duckdb.connect()
    try:
        con.register("cd", df)
        cal = calibration_sql("cd", settings.CALIBRATION_YEARS,
                              settings.MIN_CALIBRATION_CELLDAYS, shrink_m)
        con.execute("CREATE OR REPLACE TEMP VIEW cal_raw AS " + cal)
        con.execute("CREATE OR REPLACE TEMP VIEW cal_all AS "
                    + calibration_all_sql("cal_raw", settings.MIN_CALIBRATION_CELLDAYS,
                                          shrink_m))
        out = con.execute("""
            SELECT region, platform, reference, tile_id, CAST(month AS SMALLINT) AS month, k,
                   CAST(modis_celldays AS BIGINT) AS modis_celldays,
                   CAST(viirs_celldays AS BIGINT) AS viirs_celldays, level
            FROM (SELECT * FROM cal_raw UNION ALL SELECT * FROM cal_all)
        """).df()
    finally:
        con.close()
    if not len(out):
        raise ValueError("no calibration years present in data")
    out["tile_id"] = out["tile_id"].astype("string")
    out["region"] = out["region"].astype("string")
    out["platform"] = out["platform"].astype("string")
    out["reference"] = out["reference"].astype("string")
    out["month"] = out["month"].astype("int8")
    out["k"] = out["k"].astype("float64")
    out["modis_celldays"] = out["modis_celldays"].astype("int64")
    out["viirs_celldays"] = out["viirs_celldays"].astype("int64")
    out["level"] = out["level"].astype("string")
    validate_calibration(out)
    return out


def build_harmonized(celldays, calibration, settings):
    import pandas as pd
    from firecal.contracts import validate_harmonized

    cd = celldays.copy()
    if "region" not in cd.columns:
        cd["region"] = "test"
    con = duckdb.connect()
    try:
        con.register("cd", cd)
        con.register("cal_final", calibration)
        out = con.execute(
            harmonized_sql("cd", "cal_final", settings.SERIES_START,
                           settings.SWITCH_DATE)).df()
    finally:
        con.close()
    if len(out):
        out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
        out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
        out["tile_id"] = out["tile_id"].astype("string")
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        out["value"] = out["value"].astype("float64")
        out["basis"] = out["basis"].astype("string")
    validate_harmonized(out)
    return out


def validate(celldays, calibration, settings, harmonized=None):
    cd = celldays.copy()
    if "region" not in cd.columns:
        cd["region"] = "test"
    con = duckdb.connect()
    try:
        con.register("cd", cd)
        con.register("cal_rel", calibration)
        rows = con.execute(
            monthly_sql("cd", "cal_rel", settings.SERIES_START)).fetchall()
    finally:
        con.close()
    rows = [r for r in rows if r[0] == "test"]

    def block(y0, y1):
        sub = [r for r in rows if y0 <= r[1] <= y1]
        per_year = {}
        for y in range(y0, y1 + 1):
            ys = [r for r in sub if r[1] == y]
            m = _metrics([(r[4], r[3]) for r in ys])
            m["monthly_viirs"] = [r[4] for r in ys]
            m["monthly_modis"] = [r[3] for r in ys]
            per_year[str(y)] = m
        agg = _metrics([(r[4], r[3]) for r in sub])
        agg["monthly_viirs"] = [r[4] for r in sub]
        agg["monthly_modis"] = [r[3] for r in sub]
        return {"years": list(range(y0, y1 + 1)), "metrics": agg, "per_year": per_year}

    return {
        "calibration_years": block(*settings.CALIBRATION_YEARS),
        "validation_years": block(*settings.VALIDATION_YEARS),
    }


def rebuild(settings, region=None, state=None):
    """Rebuild calibration + harmonized partitions for a region."""
    from firecal.dataset import HARMONIZED, load_state, partition_key, save_state

    state = state if state is not None else load_state(settings)
    ds_state = state.setdefault(HARMONIZED, {})
    cal_state = state.setdefault("calibration", {})
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")

    cd = read_dataset(settings, "celldays", [region] if region else None)
    shrink_m = getattr(settings, "SHRINK_M", 0)
    cal_years = settings.CALIBRATION_YEARS
    # three platform -> SNPP factors: Aqua (history), NOAA-20 and NOAA-21 (continuity)
    platforms = [("Aqua", cal_years), ("NOAA20", (2018, 2025)), ("NOAA21", (2023, 2026))]
    views = []
    for i, (platform, years) in enumerate(platforms):
        raw = calibration_sql(cd, years, settings.MIN_CALIBRATION_CELLDAYS, shrink_m,
                              platform=platform, reference="SNPP")
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_raw_{i} AS {raw}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_all_{i} AS "
                    f"{calibration_all_sql(f'cal_raw_{i}', settings.MIN_CALIBRATION_CELLDAYS, shrink_m, platform, 'SNPP')}")
        views.append(f"cal_raw_{i}")
        views.append(f"cal_all_{i}")
    con.execute("CREATE OR REPLACE TEMP VIEW cal AS "
                + " UNION ALL ".join(f"SELECT * FROM {v}" for v in views))
    # the ALL month-0 row (grand total), per platform
    con.execute("CREATE OR REPLACE TEMP VIEW cal_final AS "
                "SELECT * FROM cal "
                "UNION ALL "
                "SELECT region, platform, reference, 'ALL' AS tile_id, 0 AS month, "
                "  SUM(viirs_celldays)::DOUBLE / NULLIF(SUM(modis_celldays),0) AS k, "
                "  SUM(modis_celldays) AS modis_celldays, "
                "  SUM(viirs_celldays) AS viirs_celldays, "
                "  'all' AS level FROM cal GROUP BY region, platform, reference")

    # write calibration.parquet (single file, all regions; replace this region's rows)
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    os.makedirs(settings.DATA_PROCESSED, exist_ok=True)
    if region and os.path.exists(cal_path):
        cols = [r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{cal_path}')").fetchall()]
        if "platform" not in cols:
            # legacy single-sensor calibration file (Aqua -> SNPP only)
            new_sql = (f"SELECT * FROM cal_final UNION ALL "
                       f"SELECT region, 'Aqua' AS platform, 'SNPP' AS reference, tile_id, "
                       f"CAST(month AS SMALLINT) AS month, k, "
                       f"CAST(modis_celldays AS BIGINT), CAST(viirs_celldays AS BIGINT), level "
                       f"FROM read_parquet('{cal_path}') WHERE region != '{region}'")
        else:
            new_sql = (f"SELECT * FROM cal_final UNION ALL "
                       f"SELECT * FROM read_parquet('{cal_path}') WHERE region != '{region}'")
    else:
        new_sql = "SELECT * FROM cal_final"
    tmp = cal_path + ".tmp"
    con.execute(f"COPY ({new_sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, cal_path)

    cal_fp = fingerprint(settings.CALIBRATION_YEARS, settings.MIN_CALIBRATION_CELLDAYS,
                         settings.SHRINK_M if hasattr(settings, "SHRINK_M") else 0, region)
    rebuilt = []
    for key, meta in sorted(state.get("celldays", {}).items()):
        r, y = key.split("/")
        if region and r != region:
            continue
        year = int(y)
        part_fp = fingerprint(meta.get("fingerprint"), cal_fp)
        if ds_state.get(key, {}).get("fingerprint") == part_fp:
            continue
        harm = harmonized_sql(cd, "cal_final", settings.SERIES_START, settings.SWITCH_DATE)
        part_sql = f"SELECT * FROM ({harm}) WHERE year = {year}"
        write_partition(con, part_sql, settings, HARMONIZED, r, year)
        ds_state[key] = {"fingerprint": part_fp}
        rebuilt.append(key)
    if region:
        cal_state[region] = {"fingerprint": cal_fp}
    save_state(settings, state)
    return rebuilt
