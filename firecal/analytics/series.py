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


def seam_series(area, start, end, settings, region=None):
    import duckdb
    import os

    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")

    celldays = read_dataset(settings, "celldays", [region] if region else None)
    harmonized = read_dataset(settings, HARMONIZED, [region] if region else None)
    cell_filter = area.bbox_sql(area)
    start_s, end_s = str(start), str(end)

    # one small scan: (date, platform) counts, region-wide, for the query range
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW daily AS
        SELECT region, date_local, platform, COUNT(*)::DOUBLE AS cd
        FROM {celldays}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
        GROUP BY 1,2,3
    """)

    # region-aware sensor-outage days (same definition as rebuild-time validation)
    con.execute("""CREATE OR REPLACE TEMP VIEW aqua_d AS
        SELECT region, date_local FROM daily WHERE platform = 'Aqua'""")
    con.execute("""CREATE OR REPLACE TEMP VIEW snpp_d AS
        SELECT region, date_local FROM daily WHERE platform = 'SNPP'""")
    con.execute("""CREATE OR REPLACE TEMP VIEW outage AS
        SELECT region, date_local FROM aqua_d
        WHERE (region, date_local) NOT IN (SELECT region, date_local FROM snpp_d)
        UNION
        SELECT region, date_local FROM snpp_d
        WHERE (region, date_local) NOT IN (SELECT region, date_local FROM aqua_d)
    """)
    outage_rows = con.execute(
        "SELECT date_local FROM outage "
        + ("WHERE region = '" + region.replace("'", "''") + "' " if region else "")
        + "ORDER BY 1").fetchall()
    switch_date = getattr(settings, "SWITCH_DATE", "2012-02-01")
    outage_days = [str(r[0])[:10] for r in outage_rows
                   if str(r[0])[:10] >= switch_date]

    # raw platform cell-days per month for the area, and the S-NPP overlap per
    # month (outage days excluded), computed in ONE scan of the area's cells
    raw_rows = con.execute(f"""
        SELECT EXTRACT(year FROM cd.date_local)::INTEGER AS y,
               EXTRACT(month FROM cd.date_local)::INTEGER AS m,
               cd.platform,
               COUNT(*)::DOUBLE AS raw_n,
               COUNT(*) FILTER (WHERE NOT EXISTS (
                     SELECT 1 FROM outage o
                     WHERE o.region = cd.region AND o.date_local = cd.date_local)) AS overlap_n
        FROM {celldays} AS cd
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
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
              SELECT region, EXTRACT(year FROM date_local)::INTEGER AS y,
                     EXTRACT(month FROM date_local)::INTEGER AS m,
                     tile_id, COUNT(*)::DOUBLE AS n
              FROM {celldays}
              WHERE platform = 'Aqua'
                AND date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
                AND (region, date_local) NOT IN (SELECT region, date_local FROM outage)
                AND ({cell_filter})
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
        FROM {harmonized}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
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
    overlap_years = sorted({y for (y, m) in overlap})
    metrics = _metrics([(viirs_ov[(y, m)], aqua_k.get((y, m), 0.0) or 0.0)
                        for (y, m) in overlap])
    per_year = {}
    for y in overlap_years:
        ym = [(yy, mm) for (yy, mm) in overlap if yy == y]
        per_year[str(y)] = _metrics([(viirs_ov[(yy, mm)], aqua_k.get((yy, mm), 0.0) or 0.0)
                                     for (yy, mm) in ym])

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
            "overlap_years": overlap_years,
            "pearson_r": metrics["pearson_r"],
            "bias_pct": metrics["bias_pct"],
            "per_year": {str(y): {"pearson_r": per_year[str(y)]["pearson_r"],
                                  "bias_pct": per_year[str(y)]["bias_pct"]}
                         for y in overlap_years},
            "note": "Aqua x k vs S-NPP, months where both sensors read region-wide and "
                    "VIIRS >= 10 cell-days; sensor-outage days are excluded on both sides.",
        },
    }
