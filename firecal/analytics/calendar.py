"""Burning calendar analytics (Stage 4), C6 shape.

DuckDB over the partitioned harmonized dataset: the calendar for a 500,000 km²
area builds in about a second.
"""

import math

import pandas as pd

from firecal.dataset import read_dataset


def calendar_matrix(area, start, end, today, settings, region=None):
    """C6 calendar shape. `today` is the latest data date (never the server clock)."""
    import statistics as st
    import duckdb
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    root = read_dataset(settings, "harmonized_daily", [region] if region else None)
    cell_filter = area.bbox_sql(area)
    rows = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {root}
        WHERE date_local >= DATE '{start}' AND date_local <= DATE '{end}'
          AND ({cell_filter})
        GROUP BY 1,2
    """).fetchall()
    matrix = {}
    for y, m, v in rows:
        matrix.setdefault(y, {})[m] = float(v)

    s_dt, e_dt = pd.to_datetime(start), pd.to_datetime(end)
    all_years = list(range(s_dt.year, e_dt.year + 1))
    months = list(range(1, 13))

    def value_at(y, m):
        return matrix.get(y, {}).get(m)

    # baseline years: complete years inside the range, excluding the current year
    cur_year = pd.to_datetime(today).year
    baseline = []
    for y in all_years:
        if y == cur_year:
            continue
        if pd.Timestamp(y, 1, 1) >= s_dt and pd.Timestamp(y, 12, 31) <= e_dt:
            baseline.append(y)
    warning = (f"fewer than {settings.MIN_BASELINE_YEARS} complete years before the current year"
               if len(baseline) < settings.MIN_BASELINE_YEARS else None)

    medians, p25s, p75s = {}, {}, {}
    for m in months:
        vals = sorted(v for v in (matrix.get(y, {}).get(m) for y in baseline) if v is not None)
        if vals:
            n = len(vals)
            medians[m] = st.median(vals)
            p25s[m] = vals[int(0.25 * (n - 1))]
            p75s[m] = vals[int(0.75 * (n - 1))]
        else:
            medians[m] = None
            p25s[m] = None
            p75s[m] = None

    # partial: end before the last day of its month
    end_ts = pd.to_datetime(end).date()
    last_day = pd.Timestamp(end_ts.year, end_ts.month, 1) + pd.offsets.MonthEnd(0)
    partial = None
    if end_ts < last_day.date():
        partial = {"year": end_ts.year, "month": end_ts.month, "through_day": end_ts.day}

    matrix_out = []
    anomaly = []
    anomaly_pct = []
    annual_totals = []
    partial_years = []
    for y in all_years:
        row = []
        for m in months:
            v = value_at(y, m)
            if v is not None:
                row.append(v)
                continue
            in_range = (y > s_dt.year or (y == s_dt.year and m >= s_dt.month)) and \
                       (y < e_dt.year or (y == e_dt.year and m <= e_dt.month))
            row.append(0.0 if in_range else None)
        matrix_out.append(row)
        annual_totals.append(sum(v for v in row if v is not None))
        # partial year = the year containing `end` when partial is set
        if partial and y == partial["year"]:
            partial_years.append(y)
        a_row, p_row = [], []
        for m in months:
            v = value_at(y, m)
            med = medians[m]
            if v is None or med is None:
                a_row.append(None)
                p_row.append(None)
            else:
                a_row.append(v - med)
                p_row.append(100 * (v - med) / med if med else None)
        anomaly.append(a_row)
        anomaly_pct.append(p_row)

    return {
        "years": all_years,
        "values": matrix_out,
        "partial": partial,
        "monthly_median": [medians[m] for m in months],
        "monthly_p25": [p25s[m] for m in months],
        "monthly_p75": [p75s[m] for m in months],
        "anomaly": anomaly,
        "anomaly_pct": anomaly_pct,
        "annual_totals": annual_totals,
        "partial_years": partial_years,
        "baseline_years": baseline,
        "baseline_warning": warning,
        "coverage_warning": None,
    }
