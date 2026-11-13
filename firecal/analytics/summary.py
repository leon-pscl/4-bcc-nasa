"""Summary analytics (Stage 4): totals, peaks, current-month vs baseline median."""

import calendar as pycalendar

import pandas as pd

from firecal.analytics.stats import median, complete_years_before
from firecal.dataset import read_dataset


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

    # peak year: complete years only (full Jan-Dec inside [start, end])
    complete = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y, SUM(value) AS v
        FROM {root}
        WHERE date_local >= DATE '{start_s}' AND date_local <= DATE '{end_s}'
          AND ({cell_filter})
        GROUP BY 1
    """).fetchall()
    peak_year = None
    s_dt, e_dt = pd.to_datetime(start), pd.to_datetime(end)
    for y, v in complete:
        ts = pd.Timestamp(year=y, month=1, day=1)
        te = pd.Timestamp(year=y, month=12, day=31)
        if ts >= s_dt and te <= e_dt:
            if peak_year is None or v > peak_year[1]:
                peak_year = (y, v)

    # full-region bounds for the baseline (complete years of the record)
    rec = con.execute(f"SELECT MIN(date_local), MAX(date_local) FROM {root}").fetchone()
    rec_start, rec_end = (rec[0], rec[1]) if rec else (None, None)

    today_ts = pd.to_datetime(today)
    cur_year, cur_month, cur_day = today_ts.year, today_ts.month, today_ts.day

    # baseline years: complete years of the region's full record before the
    # current year, independent of the requested range (spec section 7)
    baseline = complete_years_before(rec_start, rec_end, cur_year)
    baseline_warning = (f"fewer than {settings.MIN_BASELINE_YEARS} complete years before the current year"
                        if len(baseline) < settings.MIN_BASELINE_YEARS else None)

    # current_month is null when today is outside [start, end]
    current_month = None
    if s_dt <= today_ts <= e_dt:
        cur_val = con.execute(f"""
            SELECT COALESCE(SUM(value), 0) FROM {root}
            WHERE date_local >= DATE '{cur_year}-{cur_month:02d}-01'
              AND date_local <= DATE '{today}'
              AND ({cell_filter})
        """).fetchone()[0]

        # same-days span: day 1..cur_day, clamped to each baseline year's month length;
        # a baseline year with no rows counts as 0, not as missing
        if baseline:
            medians = []
            for y in baseline:
                last = pycalendar.monthrange(y, cur_month)[1]
                clamped = min(cur_day, last)
                v = con.execute(f"""
                    SELECT COALESCE(SUM(value), 0) FROM {root}
                    WHERE date_local >= DATE '{y}-{cur_month:02d}-01'
                      AND date_local <= DATE '{y}-{cur_month:02d}-{clamped:02d}'
                      AND ({cell_filter})
                """).fetchone()[0]
                medians.append(v)
            med_span = median(medians)
        else:
            med_span = None
        # pct_vs_median is null when the baseline median is 0 or missing (spec 7)
        pct = (100 * (cur_val - med_span) / med_span) if med_span else None
        current_month = {
            "year": cur_year, "month": cur_month, "through_day": cur_day,
            "value": cur_val, "median_same_span": med_span, "pct_vs_median": pct,
        }

    con.close()
    return {
        "total": total,
        "peak_month": {"year": peak_month[0], "month": peak_month[1], "value": peak_month[2]} if peak_month else None,
        "peak_year": {"year": peak_year[0], "value": peak_year[1]} if peak_year else None,
        "current_month": current_month,
        "baseline_warning": baseline_warning,
        "latest_data_date": str(today),
    }
