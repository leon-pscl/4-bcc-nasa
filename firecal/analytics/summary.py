"""Summary analytics."""

from datetime import date

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings
from firecal.analytics.calendar import calendar_matrix


def summary(area: Area, start, end, today=None, settings=None):
    if settings is None:
        settings = Settings()
    if today is None:
        today = date.today()
    cal = calendar_matrix(area, start, end, today, settings)
    values = cal["values"]
    years = cal["years"]
    # total
    total = 0.0
    for row in values:
        for v in row:
            if v is not None:
                total += v
    # peak month
    peak_month = None
    for i, y in enumerate(years):
        for m in range(12):
            v = values[i][m]
            if v is None:
                continue
            if peak_month is None or v > peak_month["value"]:
                peak_month = {"year": y, "month": m + 1, "value": v}
    # peak year (complete years only)
    complete_years = [y for y in years if y != today.year]
    peak_year = None
    for y in complete_years:
        idx = years.index(y)
        vt = sum(v for v in values[idx] if v is not None)
        if peak_year is None or vt > peak_year["value"]:
            peak_year = {"year": y, "value": vt}
    # current month partial
    cm = today.month
    cy = today.year
    # value from day1 to today in current year/month not available at day granularity in matrix; use matrix month value as proxy
    current_val = 0.0
    if cy in years:
        current_val = values[years.index(cy)][cm - 1] or 0.0
    median_same_span = cal["monthly_median"][cm - 1]
    pct = (100 * (current_val - median_same_span) / median_same_span) if median_same_span else 0.0

    return {
        "total": total,
        "peak_month": peak_month,
        "peak_year": peak_year,
        "current_month": {
            "year": cy, "month": cm, "through_day": today.day,
            "value": current_val, "median_same_span": median_same_span,
            "pct_vs_median": pct,
        },
        "latest_data_date": str(pd_to_date(end)),
        "synthetic": False,
    }


def pd_to_date(v):
    import pandas as pd
    return pd.to_datetime(v).date()