"""Calendar matrix analytics."""

from datetime import date

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.analytics.query import area_where
from firecal.config import Settings


def _path(settings):
    return f"{settings.DATA_PROCESSED}/harmonized_daily.parquet"


def calendar_matrix(area: Area, start, end, today=None, settings=None):
    if settings is None:
        settings = Settings()
    if today is None:
        today = date.today()
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    grid = settings.GRID_DEG

    con = duckdb.connect()
    params = []
    where_area, params = area_where(area, grid, params)
    q = f"""
        SELECT (EXTRACT(YEAR FROM date_local))::INT AS yr,
               (EXTRACT(MONTH FROM date_local))::INT AS mo,
               SUM(value) AS v
        FROM read_parquet('{_path(settings)}')
        WHERE date_local BETWEEN ? AND ?
          AND {where_area}
        GROUP BY yr, mo
    """
    params = [start_d, end_d] + params
    agg = con.execute(q, params).df()
    con.close()

    years = list(range(start_d.year, end_d.year + 1))
    values = []
    for y in years:
        row = []
        for m in range(1, 13):
            if (y == start_d.year and m < start_d.month) or (y == end_d.year and m > end_d.month):
                row.append(None)
                continue
            sub = agg[(agg["yr"] == y) & (agg["mo"] == m)]
            row.append(float(sub["v"].iloc[0]) if not sub.empty else 0.0)
        values.append(row)

    current_year = today.year
    baseline_years = []
    for y in years:
        if y == current_year:
            continue
        if pd.Timestamp(year=y, month=1, day=1).date() >= start_d and pd.Timestamp(year=y, month=12, day=31).date() <= end_d:
            baseline_years.append(y)
    baseline_warning = None if len(baseline_years) >= settings.MIN_BASELINE_YEARS else f"fewer than {settings.MIN_BASELINE_YEARS} complete baseline years"

    # full grid
    full_index = pd.MultiIndex.from_product([baseline_years, range(1, 13)], names=["yr", "mo"])
    if baseline_years:
        base = agg[agg["yr"].isin(baseline_years)].set_index(["yr", "mo"])["v"].reindex(full_index, fill_value=0.0).reset_index(name="v")
    else:
        base = pd.DataFrame(columns=["yr", "mo", "v"])

    monthly_median = []
    monthly_p25 = []
    monthly_p75 = []
    for m in range(1, 13):
        vals = base[base["mo"] == m]["v"].tolist() if not base.empty else []
        if vals:
            monthly_median.append(float(pd.Series(vals).median()))
            monthly_p25.append(float(pd.Series(vals).quantile(0.25)))
            monthly_p75.append(float(pd.Series(vals).quantile(0.75)))
        else:
            monthly_median.append(0.0)
            monthly_p25.append(0.0)
            monthly_p75.append(0.0)

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

    partial = None
    if end_d.month < 12 or end_d.day < 28:
        partial = {"year": end_d.year, "month": end_d.month, "through_day": end_d.day}

    partial_years = []
    if start_d.month != 1 or start_d.day != 1:
        partial_years.append(start_d.year)
    if end_d.month != 12 or end_d.day != 31:
        partial_years.append(end_d.year)
    partial_years = sorted(set(partial_years))

    # synthetic flag from coverage
    synthetic = _synthetic_for_area(area, settings)

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
        "partial_years": partial_years,
        "baseline_years": baseline_years,
        "baseline_warning": baseline_warning,
        "coverage_warning": None,
        "synthetic": synthetic,
    }


def _synthetic_for_area(area, settings):
    import json
    from pathlib import Path
    p = Path(settings.DATA_PROCESSED) / "coverage.json"
    if not p.exists():
        return False
    try:
        cov = json.loads(p.read_text())
    except Exception:
        return False
    for c in cov:
        # overlap check simple: bbox intersect
        if area.kind == "bbox":
            w, s, e, n = area.bbox
            cw, cs, ce, cn = c["bbox"]
            if not (ce <= w or cw >= e or cn <= s or cs >= n):
                if c.get("synthetic"):
                    return True
        else:
            # point: check if inside coverage bbox
            w, s, e, n = c["bbox"]
            if w <= area.lon < e and s <= area.lat < n and c.get("synthetic"):
                return True
    return False