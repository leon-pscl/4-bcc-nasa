"""DuckDB harmonization (C3 calibration, C4 harmonized daily, C5 validation).

All the work is SQL: calibration factors per tile x month, the harmonized daily
series and the validation metrics. Output is Hive-partitioned by (region, year).
"""

import json
import math

import duckdb

from firecal.dataset import fingerprint, read_dataset, write_partition


def base_counts_sql(cd, cal_years):
    return f"""
    SELECT region, tile_id, EXTRACT(month FROM date_local)::INTEGER AS month, platform,
           COUNT(*) AS n
    FROM {cd}
    WHERE year(date_local) BETWEEN {cal_years[0]} AND {cal_years[1]}
      AND platform IN ('Aqua','SNPP')
    GROUP BY 1,2,3,4
    """


def calibration_sql(cd, cal_years, min_cal):
    """C3: k = SNPP cell-days / Aqua cell-days per tile x month, with fallbacks."""
    return f"""
    WITH c AS ({base_counts_sql(cd, cal_years)}),
    a AS (SELECT tile_id, month, region, SUM(n) AS aqua FROM c WHERE platform='Aqua' GROUP BY 1,2,3),
    s AS (SELECT tile_id, month, region, SUM(n) AS viirs FROM c WHERE platform='SNPP' GROUP BY 1,2,3),
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
             COALESCE(gt.aqua,0) AS g_aqua, COALESCE(gt.viirs,0) AS g_viirs
      FROM m
      LEFT JOIN tile_tot tt ON tt.tile_id=m.tile_id AND tt.region=m.region
      LEFT JOIN month_tot mt ON mt.month=m.month AND mt.region=m.region
      LEFT JOIN all_tot gt ON gt.region=m.region
    )
    SELECT region, tile_id, month,
      CASE WHEN aqua >= {min_cal} THEN viirs::DOUBLE/aqua
           WHEN t_aqua >= {min_cal} THEN t_viirs::DOUBLE/t_aqua
           WHEN m_aqua >= {min_cal} THEN m_viirs::DOUBLE/m_aqua
           ELSE g_viirs::DOUBLE/g_aqua END AS k,
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
    FROM base
    """


def calibration_all_sql(cal_rel, min_cal):
    """The 'ALL' fallback rows: months 1-12 (all_month) and month 0 (all)."""
    return f"""
    WITH t AS (SELECT * FROM {cal_rel})
    SELECT region, 'ALL' AS tile_id, month,
      CASE WHEN modis_celldays >= {min_cal} THEN viirs_celldays::DOUBLE/modis_celldays
           ELSE NULL END AS k,
      modis_celldays, viirs_celldays,
      CASE WHEN modis_celldays >= {min_cal} THEN 'all_month' ELSE 'all' END AS level
    FROM (
      SELECT region, month, SUM(modis_celldays) AS modis_celldays,
             SUM(viirs_celldays) AS viirs_celldays
      FROM t WHERE level = 'tile_month' GROUP BY 1,2
    )
    """


def harmonized_sql(cd, cal_rel, series_start, switch_date):
    """C4: harmonized daily series per cell (no sensor/platform)."""
    return f"""
    WITH cd AS (
      SELECT region, cell_lat_idx, cell_lon_idx, tile_id, date_local, platform,
             EXTRACT(month FROM date_local)::INTEGER AS month
      FROM {cd} WHERE date_local >= DATE '{series_start}'
    ),
    k AS (
      SELECT region, tile_id, month, k FROM {cal_rel}
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, tile_id, month ORDER BY
        CASE level WHEN 'tile_month' THEN 1 WHEN 'tile' THEN 2 WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    k_all_month AS (
      SELECT region, month, k FROM {cal_rel} WHERE tile_id = 'ALL' AND month BETWEEN 1 AND 12
    ),
    k_all AS (SELECT region, k FROM {cal_rel} WHERE tile_id = 'ALL' AND month = 0),
    aqua AS (
      SELECT cd.*, COALESCE(k.k, km.k, ka.k) AS k
      FROM cd
      LEFT JOIN k ON k.region=cd.region AND k.tile_id=cd.tile_id AND k.month=cd.month
      LEFT JOIN k_all_month km ON km.region=cd.region AND km.month=cd.month
      LEFT JOIN k_all ka ON ka.region=cd.region
      WHERE cd.platform = 'Aqua'
    ),
    snpp AS (SELECT * FROM cd WHERE platform = 'SNPP'),
    snpp_dates AS (SELECT DISTINCT region, date_local FROM snpp),
    aqua_dates AS (SELECT DISTINCT region, date_local FROM aqua),
    outage AS (SELECT region, date_local FROM aqua_dates
               WHERE (region, date_local) NOT IN (SELECT region, date_local FROM snpp_dates))
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
           k AS value, 'modis_gapfill' AS basis
      FROM aqua WHERE date_local >= DATE '{switch_date}'
        AND (region, date_local) IN (SELECT region, date_local FROM outage)
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
      SELECT region, tile_id, month, k FROM {cal_rel}
      QUALIFY ROW_NUMBER() OVER (PARTITION BY region, tile_id, month ORDER BY
        CASE level WHEN 'tile_month' THEN 1 WHEN 'tile' THEN 2 WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    k_all_month AS (
      SELECT region, month, k FROM {cal_rel} WHERE tile_id='ALL' AND month BETWEEN 1 AND 12
    ),
    k_all AS (SELECT region, k FROM {cal_rel} WHERE tile_id='ALL' AND month=0),
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
    cal_sql = calibration_sql(cd, settings.CALIBRATION_YEARS, settings.MIN_CALIBRATION_CELLDAYS)
    con.execute(f"CREATE OR REPLACE TEMP VIEW cal_raw AS {cal_sql}")
    con.execute(f"CREATE OR REPLACE TEMP VIEW cal_all AS "
                f"{calibration_all_sql('cal_raw', settings.MIN_CALIBRATION_CELLDAYS)}")
    con.execute("CREATE OR REPLACE TEMP VIEW cal AS "
                "SELECT * FROM cal_raw UNION ALL SELECT * FROM cal_all")
    # the ALL month-0 row (grand total)
    con.execute("CREATE OR REPLACE TEMP VIEW cal_final AS "
                "SELECT * FROM cal "
                "UNION ALL "
                "SELECT region, 'ALL' AS tile_id, 0 AS month, "
                "  SUM(CASE WHEN level='tile_month' THEN viirs_celldays ELSE 0 END)::DOUBLE / "
                "  NULLIF(SUM(CASE WHEN level='tile_month' THEN modis_celldays ELSE 0 END),0) AS k, "
                "  SUM(CASE WHEN level='tile_month' THEN modis_celldays ELSE 0 END) AS modis_celldays, "
                "  SUM(CASE WHEN level='tile_month' THEN viirs_celldays ELSE 0 END) AS viirs_celldays, "
                "  'all' AS level FROM cal_raw GROUP BY region")

    cal_fp = fingerprint(settings.CALIBRATION_YEARS, settings.MIN_CALIBRATION_CELLDAYS)
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
