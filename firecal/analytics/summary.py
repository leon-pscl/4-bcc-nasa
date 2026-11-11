"""Summary analytics."""

import math
from datetime import date

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings
from firecal.analytics.calendar import calendar_matrix


def _daily_path(settings):
    return f"{settings.DATA_PROCESSED}/harmonized_daily.parquet"


def summary(area: Area, start, end, today=None, settings=None):
    if settings is None:
        settings = Settings()
    if today is None:
        today = date.today()
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()

    cal = calendar_matrix(area, start, end, today, settings)
    values = cal["values"]
    years = cal["years"]

    total = 0.0
    for row in values:
        for v in row:
            if v is not None:
                total += v

    peak_month = None
    for i, y in enumerate(years):
        for m in range(12):
            v = values[i][m]
            if v is None:
                continue
            if peak_month is None or v > peak_month["value"]:
                peak_month = {"year": y, "month": m + 1, "value": v}

    complete_years = [y for y in years if (pd.Timestamp(year=y, month=1, day=1).date() >= start_d
                                         and pd.Timestamp(year=y, month=12, day=31).date() <= end_d)]
    peak_year = None
    for y in complete_years:
        idx = years.index(y)
        vt = sum(v for v in values[idx] if v is not None)
        if peak_year is None or vt > peak_year["value"]:
            peak_year = {"year": y, "value": vt}

    # latest data date = max date_local in data (filtered to area)
    con = duckdb.connect()
    grid = settings.GRID_DEG
    # bounding filter by cell indices not trivial; load area cells via python? Use all then filter
    df = con.execute(f"SELECT date_local FROM read_parquet('{_daily_path(settings)}')").df()
    con.close()
    # filter area by cell centers
    def in_area_row(r):
        ci = int(__import__("math").floor(0))  # placeholder
        return True
    # simpler: filter in python using area
    def cell_of(lat_idx, lon_idx):
        return area.contains_cell(int(lat_idx), int(lon_idx), grid)
    # need lat/lon indices; query includes them
    con = duckdb.connect()
    df = con.execute(f"SELECT cell_lat_idx, cell_lon_idx, date_local FROM read_parquet('{_daily_path(settings)}')").df()
    con.close()
    mask = [area.contains_cell(int(r["cell_lat_idx"]), int(r["cell_lon_idx"]), grid) for r in df.to_dict("records")]
    df = df[mask]
    latest = df["date_local"].max() if not df.empty else end_d
    latest_data_date = pd.to_datetime(latest).date()

    # current month
    current_month = None
    if start_d <= today <= end_d:
        cy, cm, cd = today.year, today.month, today.day
        # value: sum day 1..cd current month
        con = duckdb.connect()
        ddf = con.execute(f"""
            SELECT date_local, value FROM read_parquet('{_daily_path(settings)}')
            WHERE date_local BETWEEN ? AND ?
        """, [date(cy, cm, 1), date(cy, cm, cd)]).df()
        con.close()
        mask = ddf.index >= 0
        # filter area
        # need cell info; requery with cells
        con = duckdb.connect()
        ddf = con.execute(f"""
            SELECT cell_lat_idx, cell_lon_idx, date_local, value FROM read_parquet('{_daily_path(settings)}')
            WHERE date_local BETWEEN ? AND ?
        """, [date(cy, cm, 1), date(cy, cm, cd)]).df()
        con.close()
        ddf = ddf[[area.contains_cell(int(r["cell_lat_idx"]), int(r["cell_lon_idx"]), grid) for r in ddf.to_dict("records")]]
        value = float(ddf["value"].sum()) if not ddf.empty else 0.0

        # median same span across baseline years
        vals = []
        for y in cal["baseline_years"]:
            con = duckdb.connect()
            bdf = con.execute(f"""
                SELECT cell_lat_idx, cell_lon_idx, date_local, value FROM read_parquet('{_daily_path(settings)}')
                WHERE date_local BETWEEN ? AND ?
            """, [date(y, cm, 1), date(y, cm, min(cd, 28 if cm == 2 else 31))]).df()
            # adjust through_day
            con.close()
            # filter days <= cd
            bdf["date_local"] = pd.to_datetime(bdf["date_local"]).dt.date
            bdf = bdf[[dd.day <= cd for dd in bdf["date_local"]]]
            bdf = bdf[[area.contains_cell(int(r["cell_lat_idx"]), int(r["cell_lon_idx"]), grid) for r in bdf.to_dict("records")]]
            vals.append(float(bdf["value"].sum()) if not bdf.empty else 0.0)
        median_same_span = float(pd.Series(vals).median()) if vals else 0.0
        pct = None if median_same_span == 0 else float(100 * (value - median_same_span) / median_same_span)
        current_month = {
            "year": cy, "month": cm, "through_day": cd,
            "value": value, "median_same_span": median_same_span,
            "pct_vs_median": pct,
        }

    # partial
    partial = None
    if end_d.month < 12 or end_d.day < 28:
        partial = {"year": end_d.year, "month": end_d.month, "through_day": end_d.day}
    # partial_years
    partial_years = []
    if start_d.month != 1 or start_d.day != 1:
        partial_years.append(start_d.year)
    if end_d.month != 12 or end_d.day != 31:
        partial_years.append(end_d.year)
    partial_years = sorted(set(partial_years))

    cal["partial"] = partial
    cal["partial_years"] = partial_years

    return {
        "total": total,
        "peak_month": peak_month,
        "peak_year": peak_year,
        "current_month": current_month,
        "latest_data_date": str(latest_data_date),
        "synthetic": __import__("firecal.analytics.calendar", fromlist=["_synthetic_for_area"])._synthetic_for_area(area, settings),
    }