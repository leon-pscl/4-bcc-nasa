"""Summary analytics (Stage 4): totals, peaks, current-month vs baseline median."""

import pandas as pd

from firecal.dataset import read_dataset


def _rows_for_area(area, path, start, end, con):
    root = path
    extra = ""
    cell_filter = area.bbox_sql(area)
    sql = f"""
        SELECT date_local, value FROM {root}
        WHERE date_local >= DATE '{start}' AND date_local <= DATE '{end}'
          AND ({cell_filter})
    """
    return con.execute(sql).fetchall()


def summary(area, start, end, today, settings, region=None):
    """C6 summary shape. `today` is the latest data date (never the server clock)."""
    import duckdb
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    root = read_dataset(settings, "harmonized_daily", [region] if region else None)
    start_s = str(start)
    end_s = str(end)

    cell_filter = area.bbox_sql(area)
    total = con.execute(f"""
        SELECT SUM(value) FROM {root}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
    """).fetchone()[0] or 0.0

    peak_month = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {root}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
        GROUP BY 1,2 ORDER BY v DESC LIMIT 1
    """).fetchone()

    peak_year = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y, SUM(value) AS v
        FROM {root}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
        GROUP BY 1 ORDER BY v DESC LIMIT 1
    """).fetchone()

    today_ts = pd.to_datetime(today)
    cur_year = today_ts.year
    cur_month = today_ts.month
    cur_day = today_ts.day
    cur_val = con.execute(f"""
        SELECT SUM(value) FROM {root}
        WHERE date_local >= DATE '{cur_year}-{cur_month:02d}-01'
          AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
    """).fetchone()[0] or 0.0

    # median of the same day span in complete baseline years
    baseline = []
    s_dt, e_dt = pd.to_datetime(start), pd.to_datetime(end)
    y = s_dt.year
    while y <= e_dt.year:
        if pd.Timestamp(y, 1, 1) >= s_dt and pd.Timestamp(y, 12, 31) <= e_dt and y != cur_year:
            baseline.append(y)
        y += 1
    medians = []
    for y in baseline:
        v = con.execute(f"""
            SELECT SUM(value) FROM {root}
            WHERE date_local >= DATE '{y}-{cur_month:02d}-01'
              AND date_local <= DATE '{y}-{cur_month:02d}-{cur_day:02d}'
              AND ({cell_filter})
        """).fetchone()[0]
        if v is not None:
            medians.append(v)
    med_span = sorted(medians)[len(medians) // 2] if medians else None
    pct = (100 * (cur_val - med_span) / med_span) if med_span else None

    return {
        "total": total,
        "peak_month": {"year": peak_month[0], "month": peak_month[1], "value": peak_month[2]} if peak_month else None,
        "peak_year": {"year": peak_year[0], "value": peak_year[1]} if peak_year else None,
        "current_month": {
            "year": cur_year, "month": cur_month, "through_day": cur_day,
            "value": cur_val, "median_same_span": med_span, "pct_vs_median": pct,
        },
        "latest_data_date": str(today),
    }
