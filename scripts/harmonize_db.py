"""Harmonization (C3/C4) over DuckDB, for large cell-day tables."""

import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--celldays", required=True)
    ap.add_argument("--out-calibration", required=True)
    ap.add_argument("--out-harmonized", required=True)
    ap.add_argument("--out-validation", required=True)
    ap.add_argument("--series-start", default="2003-01-01")
    ap.add_argument("--switch-date", default="2012-02-01")
    ap.add_argument("--cal-years", default="2013:2017")
    ap.add_argument("--val-years", default="2018:2021")
    ap.add_argument("--min-cal-celldays", type=int, default=30)
    ap.add_argument("--tile-deg", type=float, default=1.0)
    args = ap.parse_args()

    c0, c1 = (int(x) for x in args.cal_years.split(":"))
    v0, v1 = (int(x) for x in args.val_years.split(":"))
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    t0 = time.time()

    cd = "read_parquet('" + args.celldays + "')"

    # --- C3 calibration: k = SNPP cell-days / Aqua cell-days per tile x month
    cal_sql = f"""
    WITH c AS (
      SELECT tile_id, EXTRACT(month FROM date_local)::INTEGER AS month, platform, COUNT(*) AS n FROM {cd}
      WHERE year(date_local) BETWEEN {c0} AND {c1} AND platform IN ('Aqua','SNPP')
      GROUP BY 1,2,3
    ), a AS (
      SELECT tile_id, month, SUM(n) AS aqua FROM c WHERE platform='Aqua' GROUP BY 1,2
    ), s AS (
      SELECT tile_id, month, SUM(n) AS viirs FROM c WHERE platform='SNPP' GROUP BY 1,2
    ), m AS (
      SELECT COALESCE(a.tile_id,s.tile_id) AS tile_id, COALESCE(a.month,s.month) AS month,
             COALESCE(a.aqua,0) AS aqua, COALESCE(s.viirs,0) AS viirs
      FROM a FULL OUTER JOIN s ON a.tile_id=s.tile_id AND a.month=s.month
    ), tile_tot AS (
      SELECT tile_id, SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m GROUP BY 1
    ), month_tot AS (
      SELECT month, SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m GROUP BY 1
    ), all_tot AS (SELECT SUM(aqua) AS aqua, SUM(viirs) AS viirs FROM m)
    SELECT m.tile_id, m.month,
      CASE WHEN m.aqua >= {args.min_cal_celldays} THEN m.viirs::DOUBLE/m.aqua
           WHEN tt.aqua >= {args.min_cal_celldays} THEN tt.viirs::DOUBLE/tt.aqua
           WHEN mt.aqua >= {args.min_cal_celldays} THEN mt.viirs::DOUBLE/mt.aqua
           ELSE gt.viirs::DOUBLE/gt.aqua END AS k,
      CASE WHEN m.aqua >= {args.min_cal_celldays} THEN m.aqua
           WHEN tt.aqua >= {args.min_cal_celldays} THEN tt.aqua
           WHEN mt.aqua >= {args.min_cal_celldays} THEN mt.aqua
           ELSE gt.aqua END AS modis_celldays,
      CASE WHEN m.aqua >= {args.min_cal_celldays} THEN m.viirs
           WHEN tt.aqua >= {args.min_cal_celldays} THEN tt.viirs
           WHEN mt.aqua >= {args.min_cal_celldays} THEN mt.viirs
           ELSE gt.viirs END AS viirs_celldays,
      CASE WHEN m.aqua >= {args.min_cal_celldays} THEN 'tile_month'
           WHEN tt.aqua >= {args.min_cal_celldays} THEN 'tile'
           WHEN mt.aqua >= {args.min_cal_celldays} THEN 'all_month'
           ELSE 'all' END AS level
    FROM m
    JOIN tile_tot tt ON tt.tile_id = m.tile_id
    JOIN month_tot mt ON mt.month = m.month
    CROSS JOIN all_tot gt
    """
    con.execute(f"CREATE OR REPLACE TEMP VIEW base_counts AS "
                f"SELECT tile_id, EXTRACT(month FROM date_local)::INTEGER AS month, platform, COUNT(*) AS n FROM {cd} "
                f"WHERE year(date_local) BETWEEN {c0} AND {c1} AND platform IN ('Aqua','SNPP') GROUP BY 1,2,3")
    con.execute("CREATE OR REPLACE TEMP VIEW all_tot AS "
                "SELECT SUM(CASE WHEN platform='Aqua' THEN n ELSE 0 END) AS aqua, "
                "SUM(CASE WHEN platform='SNPP' THEN n ELSE 0 END) AS viirs FROM base_counts")
    con.execute(f"CREATE OR REPLACE TEMP VIEW cal AS {cal_sql}")
    # ALL rows: month 1-12 (all_month) and month 0 (all)
    all_month_sql = f"""
    SELECT 'ALL' AS tile_id, month,
      CASE WHEN modis_celldays >= {args.min_cal_celldays}
           THEN viirs_celldays::DOUBLE/modis_celldays ELSE NULL END AS k,
      modis_celldays, viirs_celldays,
      CASE WHEN modis_celldays >= {args.min_cal_celldays} THEN 'all_month' ELSE 'all' END AS level
    FROM (SELECT month, SUM(modis_celldays) AS modis_celldays, SUM(viirs_celldays) AS viirs_celldays
          FROM cal GROUP BY 1)
    """
    all_all_sql = f"""
    SELECT 'ALL' AS tile_id, 0 AS month, viirs::DOUBLE/aqua AS k,
           aqua AS modis_celldays, viirs AS viirs_celldays, 'all' AS level FROM all_tot gt
    """
    con.execute(f"CREATE OR REPLACE TEMP VIEW cal_all_month AS {all_month_sql}")
    con.execute(f"CREATE OR REPLACE TEMP VIEW cal_all_all AS {all_all_sql}")
    # fix all_month nulls using the all-level factor
    con.execute(f"""
    CREATE OR REPLACE TEMP VIEW cal_final AS
    SELECT tile_id, month, k, modis_celldays, viirs_celldays, level FROM cal
    UNION ALL
    SELECT tile_id, month, COALESCE(k, (SELECT k FROM cal_all_all)), modis_celldays, viirs_celldays, level FROM cal_all_month
    UNION ALL
    SELECT tile_id, month, k, modis_celldays, viirs_celldays, level FROM cal_all_all
    """)
    con.execute(f"COPY (SELECT tile_id, CAST(month AS SMALLINT) AS month, k, "
                f"CAST(modis_celldays AS BIGINT) AS modis_celldays, "
                f"CAST(viirs_celldays AS BIGINT) AS viirs_celldays, level FROM cal_final) "
                f"TO '{args.out_calibration}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print("calibration done", time.time() - t0, flush=True)

    # --- C4 harmonized
    harm_sql = f"""
    WITH cd AS (
      SELECT cell_lat_idx, cell_lon_idx, tile_id, date_local, platform,
             EXTRACT(month FROM date_local)::INTEGER AS month,
             EXTRACT(year FROM date_local)::INTEGER AS year
      FROM {cd} WHERE date_local >= DATE '{args.series_start}'
    ),
    k AS (
      SELECT c.tile_id, c.month, c.k FROM cal_final c
      QUALIFY ROW_NUMBER() OVER (PARTITION BY c.tile_id, c.month ORDER BY
        CASE c.level WHEN 'tile_month' THEN 1 WHEN 'tile' THEN 2 WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    ),
    aqua AS (
      SELECT cd.*, k.k FROM cd JOIN k ON k.tile_id=cd.tile_id AND k.month=cd.month WHERE cd.platform='Aqua'
    ),
    snpp AS (
      SELECT cd.* FROM cd WHERE cd.platform='SNPP'
    ),
    snpp_dates AS (SELECT DISTINCT date_local FROM snpp),
    aqua_dates AS (SELECT DISTINCT date_local FROM aqua),
    outage AS (SELECT date_local FROM aqua_dates WHERE date_local NOT IN (SELECT date_local FROM snpp_dates))
    SELECT cell_lat_idx, cell_lon_idx, tile_id, date_local, k AS value, 'modis_scaled' AS basis
      FROM aqua WHERE date_local < DATE '{args.switch_date}'
    UNION ALL
    SELECT cell_lat_idx, cell_lon_idx, tile_id, date_local, 1.0 AS value, 'viirs' AS basis
      FROM snpp WHERE date_local >= DATE '{args.switch_date}'
    UNION ALL
    SELECT cell_lat_idx, cell_lon_idx, tile_id, date_local, k AS value, 'modis_gapfill' AS basis
      FROM aqua WHERE date_local >= DATE '{args.switch_date}' AND date_local IN (SELECT date_local FROM outage)
    """
    con.execute(f"COPY ({harm_sql}) TO '{args.out_harmonized}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print("harmonized done", time.time() - t0, flush=True)

    # temp views reused by the validation query
    con.execute(f"CREATE OR REPLACE TEMP VIEW cd_v AS "
                f"SELECT cell_lat_idx, cell_lon_idx, tile_id, date_local, platform, "
                f"EXTRACT(month FROM date_local)::INTEGER AS month, "
                f"EXTRACT(year FROM date_local)::INTEGER AS year FROM {cd} "
                f"WHERE date_local >= DATE '{args.series_start}'")
    con.execute("CREATE OR REPLACE TEMP VIEW k AS "
                "SELECT tile_id, month, k FROM cal_final QUALIFY ROW_NUMBER() OVER "
                "(PARTITION BY tile_id, month ORDER BY CASE level WHEN 'tile_month' THEN 1 "
                "WHEN 'tile' THEN 2 WHEN 'all_month' THEN 3 ELSE 4 END) = 1")
    # --- C5 validation
    val_sql = f"""
    WITH cd AS (
      SELECT platform, date_local, tile_id,
             EXTRACT(month FROM date_local)::INTEGER AS month,
             EXTRACT(year FROM date_local)::INTEGER AS year
      FROM cd_v
    ),
    snpp_dates AS (SELECT DISTINCT date_local FROM cd WHERE platform='SNPP'),
    aqua_dates AS (SELECT DISTINCT date_local FROM cd WHERE platform='Aqua'),
    outage AS (SELECT date_local FROM aqua_dates WHERE date_local NOT IN (SELECT date_local FROM snpp_dates)),
    aqua_k AS (
      SELECT cd.year, cd.month, cd.tile_id, COUNT(*)::DOUBLE AS n, k.k
      FROM cd JOIN k ON k.tile_id=cd.tile_id AND k.month=cd.month
      WHERE cd.platform='Aqua' AND cd.date_local NOT IN (SELECT date_local FROM outage)
      GROUP BY 1,2,3,5
    ),
    modis_m AS (SELECT year, month, SUM(n*k) AS monthly_modis FROM aqua_k GROUP BY 1,2),
    viirs_m AS (SELECT year, month, COUNT(*)::DOUBLE AS monthly_viirs FROM cd WHERE platform='SNPP' GROUP BY 1,2),
    joined AS (SELECT m.year, m.month, m.monthly_modis, v.monthly_viirs FROM modis_m m JOIN viirs_m v USING (year, month))
    SELECT year, month, monthly_viirs, monthly_modis FROM joined ORDER BY year, month
    """
    con.execute(f"CREATE OR REPLACE TEMP VIEW monthly AS {val_sql}")
    rows = con.execute("SELECT * FROM monthly").fetchall()
    import json, math

    def metrics(sub):
        v = [r[2] for r in sub]
        m = [r[3] for r in sub]
        idx = [i for i in range(len(v)) if v[i] >= 10]
        if len(idx) < 2:
            return {"pearson_r": 0.0, "bias_pct": 0.0, "median_abs_pct_error": 0.0}
        vv = [v[i] for i in idx]
        mm = [m[i] for i in idx]
        n = len(vv)
        mv = sum(vv) / n
        mmv = sum(mm) / n
        cov = sum((vv[i] - mv) * (mm[i] - mmv) for i in range(n)) / n
        sv = math.sqrt(sum((x - mv) ** 2 for x in vv) / n)
        sm = math.sqrt(sum((x - mmv) ** 2 for x in mm) / n)
        r = cov / (sv * sm) if sv and sm else 0.0
        bias = (mmv - mv) / mv * 100 if mv else 0.0
        errs = sorted(abs((mm[i] - vv[i]) / (vv[i] if vv[i] else 1)) * 100 for i in range(n))
        mape = errs[len(errs) // 2]
        return {"pearson_r": r, "bias_pct": bias, "median_abs_pct_error": mape}

    def block(y0, y1):
        sub = [r for r in rows if y0 <= r[0] <= y1]
        per_year = {}
        for y in range(y0, y1 + 1):
            ys = [r for r in sub if r[0] == y]
            mm = metrics(ys)
            mm["monthly_viirs"] = [r[2] for r in ys]
            mm["monthly_modis"] = [r[3] for r in ys]
            per_year[str(y)] = mm
        agg = metrics(sub)
        agg["monthly_viirs"] = [r[2] for r in sub]
        agg["monthly_modis"] = [r[3] for r in sub]
        return {"years": list(range(y0, y1 + 1)), "metrics": agg, "per_year": per_year}

    out = {"calibration_years": block(c0, c1), "validation_years": block(v0, v1)}
    with open(args.out_validation, "w") as f:
        json.dump(out, f, indent=2)
    print("validation done", time.time() - t0, flush=True)
    print("calibration metrics", out["calibration_years"]["metrics"]["pearson_r"],
          out["calibration_years"]["metrics"]["bias_pct"])
    print("validation metrics", out["validation_years"]["metrics"]["pearson_r"],
          out["validation_years"]["metrics"]["bias_pct"])


if __name__ == "__main__":
    main()
