"""Monthly seam series behind /api/series.

Raw sensor cell-days, Aqua x k (the MODIS side of the seam), and the harmonized
sum, per calendar month, for an arbitrary area. The area validation block
compares Aqua x k against S-NPP over the overlap months (both sensors up
region-wide, and VIIRS >= 10 cell-days/month, the same rule as the rebuild-time
validation), with region-wide sensor-outage days excluded on both sides.

Outage days are sensor-level, not area-level: a day where exactly one of
Aqua/SNPP read at least one cell-day in the region is unusable for a ratio no
matter which area you ask about (Aqua down 2020-08-18..2020-09-02 among them).
They are reported in `outage_days`, clipped to the query range, since the
switch date.
"""

from firecal.dataset import HARMONIZED, read_dataset
from firecal.harmonize.db import _metrics


def _months_between(start, end):
    """All (year, month) tuples in [start, end], inclusive."""
    import pandas as pd
    cur = pd.Timestamp(start).replace(day=1)
    stop = pd.Timestamp(end).replace(day=1)
    out = []
    while cur <= stop:
        out.append((cur.year, cur.month))
        cur = cur + pd.offsets.MonthBegin(1)
    return out


def _k_aqua_view(con, cal_path):
    """TEMP VIEWs for the Aqua->SNPP factor, following calibration's level hierarchy."""
    cal = f"read_parquet('{cal_path.replace(chr(92), '/').replace(chr(39), chr(39) * 2)}')"
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW k_tile AS
        SELECT region, reference, tile_id, month, k FROM {cal}
        WHERE platform = 'Aqua' AND reference = 'SNPP'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY region, reference, tile_id, month
                                   ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                       WHEN 'tile' THEN 2
                                                       WHEN 'all_month' THEN 3 ELSE 4 END) = 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW k_am AS
        SELECT region, reference, month, k FROM {cal}
        WHERE platform = 'Aqua' AND reference = 'SNPP' AND tile_id = 'ALL' AND month BETWEEN 1 AND 12
        QUALIFY ROW_NUMBER() OVER (PARTITION BY region, reference, month ORDER BY 1) = 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW k_all AS
        SELECT region, reference, k FROM {cal}
        WHERE platform = 'Aqua' AND reference = 'SNPP' AND tile_id = 'ALL' AND month = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY region, reference ORDER BY 1) = 1
    """)


def seam_series(area, start, end, settings, region=None, cover="all"):
    import duckdb
    import os
    from firecal.analytics.cover import cover_exists

    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")

    celldays = read_dataset(settings, "celldays", [region] if region else None)
    harmonized = read_dataset(settings, HARMONIZED, [region] if region else None)
    cell_filter = area.bbox_sql(area)
    cover_pred_cd = cover_exists(settings, cover, "cd")
    cover_pred_h = cover_exists(settings, cover, "h")
    start_s, end_s = str(start), str(end)

    # one small scan: (date, platform) counts, region-wide, for the query range
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE daily AS
        SELECT region, date_local, platform, COUNT(*)::DOUBLE AS cd
        FROM {celldays} AS cd
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cover_pred_cd})
        GROUP BY 1,2,3
    """)

    # region-aware sensor-outage days (same definition as rebuild-time validation):
    # a day outage iff exactly one of Aqua/SNPP read at least one cell-day in the
    # region -- i.e. the symmetric difference, computed as a set operation
    con.execute("""CREATE OR REPLACE TEMP VIEW aqua_d AS
        SELECT region, date_local FROM daily WHERE platform = 'Aqua'""")
    con.execute("""CREATE OR REPLACE TEMP VIEW snpp_d AS
        SELECT region, date_local FROM daily WHERE platform = 'SNPP'""")
    con.execute("""CREATE OR REPLACE TEMP TABLE outage AS
        (SELECT region, date_local FROM aqua_d
         EXCEPT SELECT region, date_local FROM snpp_d)
        UNION
        (SELECT region, date_local FROM snpp_d
         EXCEPT SELECT region, date_local FROM aqua_d)
    """)
    con.execute("ANALYZE outage")
    outage_rows = con.execute(
        "SELECT date_local FROM outage "
        + ("WHERE region = '" + region.replace("'", "''") + "' " if region else "")
        + "ORDER BY 1").fetchall()
    switch_date = getattr(settings, "SWITCH_DATE", "2012-02-01")
    snpp_end = getattr(settings, "SNPP_END", "2026-11-02")
    outage_days = [str(r[0])[:10] for r in outage_rows
                   if switch_date <= str(r[0])[:10] <= snpp_end]

    # raw platform cell-days per month for the area, and the S-NPP overlap per
    # month (outage days excluded), computed in ONE scan of the area's cells
    raw_rows = con.execute(f"""
        SELECT EXTRACT(year FROM cd.date_local)::INTEGER AS y,
               EXTRACT(month FROM cd.date_local)::INTEGER AS m,
               cd.platform,
               COUNT(*)::DOUBLE AS raw_n,
               COUNT(*) FILTER (WHERE o.region IS NULL) AS overlap_n
        FROM {celldays} AS cd
        LEFT JOIN outage o ON o.region = cd.region AND o.date_local = cd.date_local
        WHERE cd.date_local >= DATE '{start_s}' AND cd.date_local <= DATE '{end_s}'
          AND ({cell_filter}) AND ({cover_pred_cd})
        GROUP BY 1,2,3
    """).fetchall()
    raw = {p: {} for p in ("Aqua", "SNPP", "NOAA20", "NOAA21")}
    viirs_ov = {}
    for y, m, p, raw_n, overlap_n in raw_rows:
        raw.setdefault(p, {})[(y, m)] = raw_n
        if p == "SNPP":
            viirs_ov[(y, m)] = overlap_n

    # Aqua x k per month (outage days excluded), joined per tile then
    # aggregated across the area
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    aqua_k = {}
    if os.path.exists(cal_path):
        _k_aqua_view(con, cal_path)
        krows = con.execute(f"""
            SELECT cd.region, cd.y, cd.m, SUM(cd.n * COALESCE(k.k, ka.k, aam.k)) AS v
            FROM (
              SELECT cd.region AS region, EXTRACT(year FROM cd.date_local)::INTEGER AS y,
                     EXTRACT(month FROM cd.date_local)::INTEGER AS m,
                     cd.tile_id, COUNT(*)::DOUBLE AS n
              FROM {celldays} AS cd
              LEFT JOIN outage o ON o.region = cd.region AND o.date_local = cd.date_local
              WHERE platform = 'Aqua'
                AND cd.date_local >= DATE '{start_s}' AND cd.date_local <= DATE '{end_s}'
                AND o.region IS NULL
                AND ({cell_filter}) AND ({cover_pred_cd})
              GROUP BY 1,2,3,4
            ) AS cd
            LEFT JOIN k_tile k ON k.region = cd.region
                              AND k.reference = 'SNPP'
                              AND k.tile_id = cd.tile_id AND k.month = cd.m
            LEFT JOIN k_am aam ON aam.region = cd.region
                              AND aam.reference = 'SNPP' AND aam.month = cd.m
            LEFT JOIN k_all ka ON ka.region = cd.region
                              AND ka.reference = 'SNPP'
            GROUP BY 1,2,3
        """).fetchall()
        for _, y, m, v in krows:
            key = (y, m)
            aqua_k[key] = aqua_k.get(key, 0.0) + v

    # harmonized sum per month
    harm_rows = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {harmonized} AS h
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter}) AND ({cover_pred_h})
        GROUP BY 1,2
    """).fetchall()
    harmonized = {(y, m): v for y, m, v in harm_rows}

    months = _months_between(start_s, end_s)
    month_keys = [f"{y}-{m:02d}" for y, m in months]

    def series(mapping):
        return [round(mapping.get((y, m), 0) or 0, 1) for y, m in months]

    # area validation over the overlap months (post-switch, both sensors up)
    overlap = [(y, m) for (y, m) in months
               if f"{y}-{m:02d}" >= switch_date[:7] and (y, m) in viirs_ov]
    cal_years = tuple(getattr(settings, "CALIBRATION_YEARS", ()) or ())
    held_out_years = tuple(getattr(settings, "VALIDATION_YEARS", ()) or ())
    all_pairs = [(y, m, viirs_ov[(y, m)], aqua_k.get((y, m), 0.0) or 0.0)
                 for (y, m) in overlap]
    held_pairs = [p for p in all_pairs if p[0] not in cal_years]
    metrics = _metrics([(p[2], p[3]) for p in held_pairs])
    per_year = {}
    for y in sorted({p[0] for p in all_pairs}):
        ym = [p for p in all_pairs if p[0] == y]
        m = _metrics([(p[2], p[3]) for p in ym])
        m["months"] = len(ym)
        per_year[str(y)] = m
    in_sample = {}
    for y in sorted({p[0] for p in all_pairs if p[0] in cal_years}):
        ym = [p for p in all_pairs if p[0] == y]
        m = _metrics([(p[2], p[3]) for p in ym])
        m["months"] = len(ym)
        in_sample[str(y)] = m
    fit_months = sum(m["months"] for m in in_sample.values())
    held_complete = [y for y in sorted({p[0] for p in held_pairs})
                     if sum(1 for p in held_pairs if p[0] == y) == 12
                     and y in held_out_years] or [y for y in sorted({p[0] for p in held_pairs})
                                                  if sum(1 for p in held_pairs if p[0] == y) == 12]
    err_years = held_complete if held_complete else sorted({p[0] for p in held_pairs})
    typical_err = None
    if err_years:
        errs = sorted(abs(per_year[str(y)]["bias_pct"]) for y in err_years)
        typical_err = float(errs[len(errs) // 2]) if len(errs) % 2 else float((errs[len(errs) // 2 - 1] + errs[len(errs) // 2]) / 2)

    con.close()
    return {
        "switch_date": switch_date,
        "months": month_keys,
        "aqua": series(raw["Aqua"]),
        "snpp": series(raw["SNPP"]),
        "noaa20": series(raw["NOAA20"]),
        "noaa21": series(raw["NOAA21"]),
        "aqua_k": series(aqua_k),
        "harmonized": series(harmonized),
        "outage_days": outage_days,
        "validation": {
            "overlap_years": sorted({p[0] for p in all_pairs}),
            "fit_years": list(cal_years),
            "held_out_years": list(held_out_years),
            "pearson_r": metrics["pearson_r"],
            "bias_pct": metrics["bias_pct"],
            "held_out_months": len(held_pairs),
            "in_sample_months": fit_months,
            "per_year": {str(y): {"pearson_r": m["pearson_r"], "bias_pct": m["bias_pct"],
                                  "months": m["months"]}
                         for y, m in per_year.items()},
            "in_sample": {str(y): {"pearson_r": m["pearson_r"], "bias_pct": m["bias_pct"],
                                   "months": m["months"]}
                          for y, m in in_sample.items()},
            "typical_year_error_pct": typical_err,
            "note": "Aqua x k vs S-NPP, months where both sensors read region-wide and "
                    "VIIRS >= 10 cell-days; sensor-outage days are excluded on both sides. "
                    "Aggregate metrics and per-year are over held-out months only "
                    "(fit_years in the calibration block); typical_year_error_pct is the "
                    "median |bias %| over held-out complete (12-month) years. "
                    f"outage_days stop at S-NPP's planned end ({snpp_end}, D15); days after "
                    "it are NOAA-20/21, not outages.",
        },
    }
