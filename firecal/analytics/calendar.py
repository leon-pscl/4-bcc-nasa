"""Calendar matrix analytics."""

from datetime import date

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings


def _harmonized_path(settings):
    return f"{settings.DATA_PROCESSED}/harmonized_daily.parquet"


def calendar_matrix(area: Area, start, end, today=None, settings=None):
    if settings is None:
        settings = Settings()
    if today is None:
        today = date.today()
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    grid = settings.GRID_DEG

    # load cells
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{_harmonized_path(settings)}')").df()
    con.close()

    # filter area
    mask = df.apply(lambda r: area.contains_cell(int(r["cell_lat_idx"]), int(r["cell_lon_idx"]), grid), axis=1)
    df = df[mask]
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date
    df = df[(df["date_local"] >= start_d) & (df["date_local"] <= end_d)]

    # aggregate per year/month
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df["month"] = pd.to_datetime(df["date_local"]).dt.month
    agg = df.groupby(["year", "month"])["value"].sum().reset_index()

    years = list(range(start_d.year, end_d.year + 1))
    # build matrix
    values = []
    for y in years:
        row = []
        for m in range(1, 13):
            if (y == start_d.year and m < start_d.month) or (y == end_d.year and m > end_d.month):
                row.append(None)
                continue
            v = agg[(agg["year"] == y) & (agg["month"] == m)]
            row.append(float(v["value"].iloc[0]) if not v.empty else 0.0)
        values.append(row)

    # baseline years: complete years inside range excluding current year
    current_year = today.year
    baseline_years = [y for y in years if y != current_year and not (y == end_d.year and end_d < pd.Timestamp(year=end_d.year, month=12, day=31).date())]
    # simpler: complete years are those fully within start..end
    baseline_years = []
    for y in years:
        if y == current_year:
            continue
        if pd.Timestamp(year=y, month=1, day=1).date() >= start_d and pd.Timestamp(year=y, month=12, day=31).date() <= end_d:
            baseline_years.append(y)
    if len(baseline_years) < settings.MIN_BASELINE_YEARS:
        baseline_warning = f"fewer than {settings.MIN_BASELINE_YEARS} complete baseline years"
    else:
        baseline_warning = None

    # monthly median/p25/p75 across baseline years
    baseline_agg = agg[agg["year"].isin(baseline_years)]
    monthly_median = []
    monthly_p25 = []
    monthly_p75 = []
    for m in range(1, 13):
        vals = baseline_agg[baseline_agg["month"] == m]["value"].tolist()
        if vals:
            monthly_median.append(float(pd.Series(vals).median()))
            monthly_p25.append(float(pd.Series(vals).quantile(0.25)))
            monthly_p75.append(float(pd.Series(vals).quantile(0.75)))
        else:
            monthly_median.append(0.0)
            monthly_p25.append(0.0)
            monthly_p75.append(0.0)

    # anomaly
    anomaly = []
    anomaly_pct = []
    for y in years:
        arow = []
        prow = []
        for m in range(1, 13):
            v = values[years.index(y)][m - 1]
            med = monthly_median[m - 1]
            if v is None:
                arow.append(None)
                prow.append(None)
            else:
                arow.append(float(v - med))
                if med == 0:
                    prow.append(None)
                else:
                    prow.append(float(100 * (v - med) / med))
        anomaly.append(arow)
        anomaly_pct.append(prow)

    annual_totals = []
    for y in years:
        vals = [v for v in values[years.index(y)] if v is not None]
        annual_totals.append(float(sum(vals)) if vals else 0.0)

    partial_years = [end_d.year] if end_d.month < 12 or end_d.day < 28 else []
    # partial if current year incomplete
    partial = {"year": end_d.year, "month": end_d.month, "through_day": end_d.day}

    return {
        "query": {"start": str(start_d), "end": str(end_d), "area_km2": area.area_km2()},
        "unit": settings.UI_UNIT_LABEL,
        "years": years,
        "values": values,
        "partial": partial,
        "monthly_median": monthly_median,
        "monthly_p25": monthly_p25,
        "monthly_p75": monthly_p75,
        "anomaly": anomaly,
        "anomaly_pct": anomaly_pct,
        "annual_totals": annual_totals,
        "partial_years": [end_d.year],
        "baseline_years": baseline_years,
        "baseline_warning": baseline_warning,
        "coverage_warning": None,
        "synthetic": False,
    }