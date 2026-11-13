"""Burning calendar analytics (Stage 4).

DuckDB over the partitioned harmonized dataset: the calendar for a 500,000 km²
area builds in about a second.
"""

import math

import pandas as pd

from firecal.dataset import read_dataset


def calendar_matrix(area, start, end, today, settings, region=None):
    import duckdb
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    root = read_dataset(settings, "harmonized_daily", [region] if region else None)
    start_s = str(start)
    end_s = str(end)
    cell_filter = area.bbox_sql(area)
    rows = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {root}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
        GROUP BY 1,2
    """).fetchall()
    matrix = {}
    for y, m, v in rows:
        matrix.setdefault(y, {})[m] = float(v)

    years = sorted(matrix) if matrix else []
    all_years = list(range(pd.to_datetime(start).year, pd.to_datetime(end).year + 1))
    months = list(range(1, 13))

    def cell_value(y, m):
        v = matrix.get(y, {}).get(m)
        return v

    # baseline years: complete years inside the range, excluding the current year
    baseline = []
    for y in all_years:
        if y == pd.to_datetime(start).year or y == pd.to_datetime(end).year:
            continue
        # a year is "complete" if the whole year is inside [start, end]
        if pd.Timestamp(year=y, month=1, day=1) >= pd.Timestamp(start) and \
           pd.Timestamp(year=y, month=12, day=31) <= pd.Timestamp(end):
            baseline.append(y)
    warning = len(baseline) < settings.MIN_BASELINE_YEARS

    medians = {}
    q25 = {}
    q75 = {}
    for m in months:
        vals = [matrix.get(y, {}).get(m) for y in baseline]
        vals = [v for v in vals if v is not None]
        if vals:
            import statistics as st
            vals_sorted = sorted(vals)
            n = len(vals_sorted)
            medians[m] = st.median(vals_sorted)
            q25[m] = vals_sorted[int(0.25 * (n - 1))]
            q75[m] = vals_sorted[int(0.75 * (n - 1))]
        else:
            medians[m] = None
            q25[m] = None
            q75[m] = None

    end_ts = pd.to_datetime(end).date()
    last_day_of_month = pd.Timestamp(end_ts.year, end_ts.month, 1) + pd.offsets.MonthEnd(0)
    partial = None
    if end_ts < last_day_of_month.date():
        partial = {"year": end_ts.year, "month": end_ts.month, "through_day": end_ts.day}

    out_matrix = {}
    for y in all_years:
        out_matrix[y] = {}
        for m in months:
            v = cell_value(y, m)
            if v is None:
                # month fully outside the range -> null
                if pd.Timestamp(y, m, 1) < pd.Timestamp(start) or pd.Timestamp(y, m, 1) > pd.Timestamp(end):
                    out_matrix[y][m] = None
                else:
                    out_matrix[y][m] = 0.0
            else:
                out_matrix[y][m] = v

    anomaly = {}
    anomaly_pct = {}
    for m in months:
        med = medians[m]
        cur = None
        this_year = pd.to_datetime(end).year
        v = matrix.get(this_year, {}).get(m)
        if med is not None and v is not None:
            anomaly[m] = v - med
            anomaly_pct[m] = (100 * (v - med) / med) if med else None
        else:
            anomaly[m] = None
            anomaly_pct[m] = None

    return {
        "matrix": {str(y): {str(m): out_matrix[y][m] for m in months} for y in all_years},
        "baseline_years": baseline,
        "median": {str(m): medians[m] for m in months},
        "q25": {str(m): q25[m] for m in months},
        "q75": {str(m): q75[m] for m in months},
        "anomaly": {str(m): anomaly[m] for m in months},
        "anomaly_pct": {str(m): anomaly_pct[m] for m in months},
        "partial": partial,
        "baseline_warning": warning,
    }
