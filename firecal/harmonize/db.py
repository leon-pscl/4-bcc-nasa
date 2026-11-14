"""DuckDB harmonization (C3 calibration, C4 harmonized daily, C5 validation).

All the work is SQL: calibration factors per tile x month, the harmonized daily
series and the validation metrics. Output is Hive-partitioned by (region, year).
"""

import json
import math
import os

import duckdb

from firecal.dataset import fingerprint, read_dataset, write_partition, PIPELINE_VERSION, SERIES_DAYS_FILE


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
             COALESCE(a.region, s.region) AS region,
             COALESCE(a.aqua,0) AS aqua, COALESCE(s.viirs,0) AS viirs
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
      CASE WHEN month = 0 THEN 'all'
           WHEN aqua >= {min_cal} THEN 'all_month'
           ELSE 'all' END AS level
    FROM (
      SELECT region, month, aqua, viirs FROM month_tot
      UNION ALL
      SELECT region, 0, aqua, viirs FROM region_tot
    ) AS u
    """


def _series_days_sql(cd, switch_date):
    """The platform the harmonized series uses each (region, date_local).

    Before SWITCH_DATE: Aqua. After it, whichever platform the series used that
    day (SNPP, else NOAA-20, else NOAA-21, else Aqua), inferred from cell-days.
    """
    return f"""
    SELECT region, date_local,
      CASE WHEN date_local < DATE '{switch_date}' THEN 'Aqua'
           WHEN has_snpp THEN 'SNPP'
           WHEN has_noaa20 THEN 'NOAA20'
           WHEN has_noaa21 THEN 'NOAA21'
           ELSE 'Aqua' END AS platform
    FROM (
      SELECT region, date_local,
             MAX(platform = 'SNPP') AS has_snpp,
             MAX(platform = 'NOAA20') AS has_noaa20,
             MAX(platform = 'NOAA21') AS has_noaa21
      FROM {cd}
      GROUP BY region, date_local
    )
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
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, month
                                 ORDER BY CASE level WHEN 'all_month' THEN 1 ELSE 2 END) = 1
    ),
    k_all AS (
      SELECT region, platform, reference, k FROM {cal_rel}
      WHERE tile_id = 'ALL' AND month = 0
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference
                                 ORDER BY CASE level WHEN 'all' THEN 1 ELSE 2 END) = 1
    ),
    k_t AS (
      SELECT region, platform, reference, tile_id, month, k FROM {cal_rel}
      WHERE platform = 'Terra' AND reference = 'Aqua'
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, tile_id, month
                                 ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                     WHEN 'tile' THEN 2
                                                     WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    k_t_am AS (
      SELECT region, platform, reference, month, k FROM {cal_rel}
      WHERE platform = 'Terra' AND reference = 'Aqua' AND tile_id = 'ALL' AND month BETWEEN 1 AND 12
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, month
                                 ORDER BY CASE level WHEN 'all_month' THEN 1 ELSE 2 END) = 1
    ),
    k_t_all AS (
      SELECT region, platform, reference, k FROM {cal_rel}
      WHERE platform = 'Terra' AND reference = 'Aqua' AND tile_id = 'ALL' AND month = 0
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference
                                 ORDER BY CASE level WHEN 'all' THEN 1 ELSE 2 END) = 1
    ),
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
    all_days AS (SELECT DISTINCT region, date_local FROM cd),
    aqua_day AS (SELECT region, date_local, COUNT(*)::INTEGER AS n FROM cd WHERE platform = 'Aqua' GROUP BY 1,2),
    aqua_spine AS (
      SELECT d.region, d.date_local, COALESCE(a.n, 0) AS n
      FROM all_days d
      LEFT JOIN aqua_day a ON a.region = d.region AND a.date_local = d.date_local
    ),
    gap AS (
      SELECT region, date_local FROM (
        SELECT region, date_local, n,
               quantile_cont(n, 0.5) OVER (PARTITION BY region ORDER BY date_local
                                          ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS a_med
        FROM aqua_spine
      ) WHERE a_med >= 5 AND n < 0.1 * a_med
    ),
    terra AS (
      SELECT cd.*, COALESCE(km.k, km_m.k, ka.k) AS k
      FROM cd
      LEFT JOIN k_t km ON km.region=cd.region AND km.platform='Terra' AND km.reference='Aqua'
                      AND km.tile_id=cd.tile_id AND km.month=cd.month
      LEFT JOIN k_t_am km_m ON km_m.region=cd.region AND km_m.platform='Terra'
                           AND km_m.reference='Aqua' AND km_m.month=cd.month
      LEFT JOIN k_t_all ka ON ka.region=cd.region AND ka.platform='Terra' AND ka.reference='Aqua'
      WHERE cd.platform = 'Terra'
        AND date_local < DATE '{switch_date}'
        AND (cd.region, date_local) IN (SELECT region, date_local FROM gap)
    ),
    snpp_dates AS (SELECT DISTINCT region, date_local FROM snpp),
    n20_dates AS (SELECT DISTINCT region, date_local FROM n20),
    n21_dates AS (SELECT DISTINCT region, date_local FROM n21),
    aqua_dates AS (SELECT DISTINCT region, date_local FROM aqua),
    SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local,
           CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
           k AS value, 'modis_scaled' AS basis
      FROM aqua WHERE date_local < DATE '{switch_date}'
        AND (region, date_local) NOT IN (
              SELECT DISTINCT region, date_local FROM terra)
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
           k AS value, 'terra_gapfill' AS basis
      FROM terra
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
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference, month
                                 ORDER BY CASE level WHEN 'all_month' THEN 1 ELSE 2 END) = 1
    ),
    k_all AS (
      SELECT region, platform, reference, k FROM {cal_rel}
      WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month=0
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, platform, reference
                                 ORDER BY CASE level WHEN 'all' THEN 1 ELSE 2 END) = 1
    ),
    snpp_dates AS (SELECT DISTINCT region, date_local FROM cd WHERE platform='SNPP'),
    aqua_dates AS (SELECT DISTINCT region, date_local FROM cd WHERE platform='Aqua'),
    -- sensor-outage days: a day where exactly one of Aqua/SNPP read at least one
    -- cell-day, region-wide (Aqua down 2020-08-18..2020-09-02, SNPP downs too);
    -- no valid ratio exists on those days, so both sides drop them
    outage AS (SELECT region, date_local FROM aqua_dates
               WHERE (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates)
               UNION
               SELECT region, date_local FROM snpp_dates
               WHERE (region, date_local) NOT IN (SELECT region, date_local FROM aqua_dates)),
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
                FROM cd WHERE platform='SNPP'
                  AND (region, date_local) NOT IN (SELECT region, date_local FROM outage)
                GROUP BY 1,2,3)
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
    con.execute("PRAGMA threads=2")
    con.execute("PRAGMA memory_limit='1500MB'")
    con.execute("PRAGMA temp_directory='data/processed/_duckdb_tmp'")

    cd = read_dataset(settings, "celldays", [region] if region else None)
    cal_years = settings.CALIBRATION_YEARS

    cal_fp = fingerprint(settings.CALIBRATION_YEARS, settings.MIN_CALIBRATION_CELLDAYS,
                         settings.SHRINK_M if hasattr(settings, "SHRINK_M") else 0, region,
                         PIPELINE_VERSION)
    cal_changed = (cal_state.get(region, {}).get("fingerprint") != cal_fp) if region else True
    if (not cal_changed) and os.path.exists(os.path.join(settings.DATA_PROCESSED, "calibration.parquet")):
        # reuse existing calibration when its inputs are unchanged (avoids re-scanning
        # 19M celldays rows on every daily update)
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_final AS "
                    f"SELECT * FROM read_parquet('{cal_path}') WHERE region = '{region}'")
    else:
        # three platform -> SNPP factors: Aqua (history), NOAA-20 and NOAA-21 (continuity)
        shrink_m = getattr(settings, "SHRINK_M", 0)
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
        # cal already carries the ALL month-0 row (from calibration_all_sql)
        con.execute("CREATE OR REPLACE TEMP VIEW cal_final AS SELECT * FROM cal")
        from firecal.harmonize.checks import check_calibration_sql
        check_calibration_sql(con, "cal_final")
    
        # write calibration.parquet (single file, all regions; replace this region's rows)
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        os.makedirs(settings.DATA_PROCESSED, exist_ok=True)
        if region and os.path.exists(cal_path):
            cols = [r[0] for r in con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)",
                [cal_path.replace(os.sep, '/')]).fetchall()]
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
                         settings.SHRINK_M if hasattr(settings, "SHRINK_M") else 0, region,
                         PIPELINE_VERSION)
    rebuilt = []

    # Terra gap-fill factors for 2003-2011 days where Aqua read almost nothing but
    # Terra was up (D20). Fitted over 2003-2011 against Aqua, same hierarchy/shrinkage.
    shrink_m = getattr(settings, "SHRINK_M", 0)
    terra_sql = calibration_sql(cd, (2003, 2011), settings.MIN_CALIBRATION_CELLDAYS,
                                shrink_m, platform="Terra", reference="Aqua")
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    try:
        have_terra = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{cal_path.replace(os.sep, '/')}') "
            f"WHERE platform = 'Terra' AND reference = 'Aqua'"
            + (f" AND region = '{region}'" if region else "")).fetchone()[0] > 0
    except Exception:
        have_terra = False
    if not have_terra:
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_terra AS {terra_sql}")
        if os.path.exists(cal_path):
            new_sql = (f"SELECT * FROM read_parquet('{cal_path.replace(os.sep, '/')}') "
                       f"WHERE NOT (platform = 'Terra' AND reference = 'Aqua'"
                       + (f" AND region = '{region}'" if region else "") + ")"
                       f" UNION ALL SELECT * FROM cal_terra")
        else:
            new_sql = "SELECT * FROM cal_terra"
        tmp = cal_path + ".terra"
        con.execute(f"COPY ({new_sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        os.replace(tmp, cal_path)
        # rebuild the temp view over the merged file so harmonized sees terra rows
        con.execute(f"CREATE OR REPLACE TEMP VIEW cal_final AS "
                    f"SELECT * FROM read_parquet('{cal_path.replace(os.sep, '/')}')"
                    + (f" WHERE region = '{region}'" if region else ""))

    def _check_harmonized_staging(con, tmp_dir):
        # check (b) on the staging copy: one row per (region, cell, date)
        from firecal.harmonize.checks import check_harmonized_sql
        import os, sys
        if not any(tmp_dir.rglob("*.parquet")):
            return  # empty partition (no rows for this year) is valid
        root = f"read_parquet('{tmp_dir.as_posix()}/region=*/year=*/*.parquet')"
        check_harmonized_sql(con, root)

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
        # staging build + check (b) before any swap; a failure leaves the old
        # partition untouched and nothing in the state file is updated
        write_partition(con, part_sql, settings, HARMONIZED, r, year,
                        post_check=_check_harmonized_staging)
        ds_state[key] = {"fingerprint": part_fp}
        rebuilt.append(key)

    # refresh series_days (region, date_local, platform the series uses that day);
    # built from all regions so a single-region rebuild can't shrink the file
    series_days_path = os.path.join(settings.DATA_PROCESSED, SERIES_DAYS_FILE)
    tmp = series_days_path + ".tmp"
    cd_all = read_dataset(settings, "celldays")
    con.execute(f"COPY ({_series_days_sql(cd_all, settings.SWITCH_DATE)}) "
                f"TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, series_days_path)

    if region:
        cal_state[region] = {"fingerprint": cal_fp}
    save_state(settings, state)
    con.close()
    return rebuilt
