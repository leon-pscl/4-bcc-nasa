"""Write frontend/public/mock/*.json from the real southeast_asia data.

The frontend develops against `/mock/*.json` (mock mode) until the API is up.
Every mock comes from the real partitioned dataset for **central_kalimantan**
(111°E-116°E, 4°S-1°N), with `synthetic: false`, so the numbers on screen are
the real ones.

Usage:  python scripts/make_mocks.py [--region southeast_asia] [--area central_kalimantan]
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb

from firecal.analytics.area import Area
from firecal.analytics.calendar import calendar_matrix
from firecal.config import Settings
from firecal.dataset import read_dataset


AREAS = {
    # name: (bbox, label)
    "central_kalimantan": ((110.7, -3.6, 115.9, 0.8), "Central Kalimantan"),
}
OUT = "frontend/public/mock"


def write(name, obj):
    os.makedirs(OUT, exist_ok=True)

    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date, datetime)):
            return str(o)
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=default)
    print("wrote", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="southeast_asia")
    ap.add_argument("--area", default="central_kalimantan")
    args = ap.parse_args()
    settings = Settings.from_env()
    bbox, label = AREAS[args.area]
    w, s, e, n = bbox
    region = args.region

    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")

    harm = read_dataset(settings, "harmonized_daily", [region])
    # latest available data date for the region
    latest = con.execute(f"SELECT MAX(date_local) FROM {harm}").fetchone()[0]
    latest_s = str(latest)
    # data version (same source the API uses)
    from firecal.dataset import data_version
    dv = data_version(settings, "harmonized_daily")

    area = Area.from_bbox(w, s, e, n)
    print("area km2:", round(area.area_km2()))

    # ---------- calendar ----------
    cal = calendar_matrix(area, "2003-01-01", latest_s, latest_s, settings, region=region)
    years = [int(y) for y in cal["matrix"]]
    values = [[cal["matrix"][str(y)][str(m + 1)] for m in range(12)] for y in years]
    anomaly = [[cal["anomaly"][str(m + 1)] for m in range(12)] for _ in years]
    # build anomaly_pct per year x month from the same source
    anomaly_pct = []
    for y in years:
        row = []
        for m in range(1, 13):
            med = cal["median"][str(m)]
            v = cal["matrix"][str(y)][str(m)]
            if med and v is not None:
                row.append(100 * (v - med) / med)
            else:
                row.append(None)
        anomaly_pct.append(row)
    annual_totals = [sum(v for v in row if v is not None) for row in values]
    partial = cal["partial"]
    partial_years = [partial["year"]] if partial else []
    baseline_years = cal["baseline_years"]

    write("calendar.json", {
        "query": {"bbox": [w, s, e, n], "start": "2003-01-01", "end": latest_s,
                  "area_km2": area.area_km2()},
        "unit": "Hotspots (harmonized)",
        "years": years,
        "values": values,
        "partial": partial,
        "monthly_median": [cal["median"][str(m)] for m in range(1, 13)],
        "monthly_p25": [cal["q25"][str(m)] for m in range(1, 13)],
        "monthly_p75": [cal["q75"][str(m)] for m in range(1, 13)],
        "anomaly": anomaly,
        "anomaly_pct": anomaly_pct,
        "annual_totals": annual_totals,
        "partial_years": partial_years,
        "baseline_years": baseline_years,
        "baseline_warning": ("Fewer than %d complete years before the current year"
                             % settings.MIN_BASELINE_YEARS) if cal["baseline_warning"] else None,
        "coverage_warning": None,
        "synthetic": False,
        "data_version": dv,
    })

    # ---------- summary ----------
    hcell = f"""cell_lon_idx * 0.05 + 0.025 BETWEEN {w} AND {e}
               AND cell_lat_idx * 0.05 + 0.025 BETWEEN {s} AND {n}"""
    tot = con.execute(f"SELECT SUM(value) FROM {harm} WHERE {hcell}").fetchone()[0]
    peak = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m, SUM(value) AS v
        FROM {harm} WHERE {hcell}
        GROUP BY 1,2 ORDER BY v DESC LIMIT 1
    """).fetchone()
    peak_year = con.execute(f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y, SUM(value) AS v
        FROM {harm} WHERE {hcell}
        GROUP BY 1 ORDER BY v DESC LIMIT 1
    """).fetchone()
    cy = latest.year
    cm = latest.month
    cm_val = con.execute(f"""
        SELECT SUM(value) FROM {harm}
        WHERE {hcell} AND EXTRACT(year FROM date_local) = {cy}
          AND EXTRACT(month FROM date_local) = {cm}
    """).fetchone()[0] or 0.0
    # median of the same day span in baseline years
    span_start = 1
    span_end = latest.day
    medians = []
    for y in baseline_years:
        v = con.execute(f"""
            SELECT SUM(value) FROM {harm}
            WHERE {hcell} AND EXTRACT(year FROM date_local) = {y}
              AND EXTRACT(month FROM date_local) = {cm}
              AND EXTRACT(day FROM date_local) BETWEEN {span_start} AND {span_end}
        """).fetchone()[0]
        if v is not None:
            medians.append(v)
    med_span = sorted(medians)[len(medians) // 2] if medians else None
    pct = (100 * (cm_val - med_span) / med_span) if med_span else None

    write("summary.json", {
        "total": tot,
        "peak_month": {"year": peak[0], "month": peak[1], "value": peak[2]},
        "peak_year": {"year": peak_year[0], "value": peak_year[1]},
        "current_month": {
            "year": cy, "month": cm, "through_day": latest.day,
            "value": cm_val, "median_same_span": med_span, "pct_vs_median": pct,
        },
        "latest_data_date": latest_s,
        "synthetic": False,
        "data_version": dv,
    })

    # ---------- map ----------
    cells = con.execute(f"""
        SELECT ROUND(cell_lat_idx*0.05 + 0.025, 4) AS lat,
               ROUND(cell_lon_idx*0.05 + 0.025, 4) AS lon,
               SUM(value) AS v
        FROM {harm} WHERE {hcell}
        GROUP BY 1,2 ORDER BY v DESC LIMIT 20000
    """).fetchall()
    write("map.json", {
        "grid_deg": 0.05,
        "aggregated_to": None,
        "cells": [{"lat": c[0], "lon": c[1], "value": c[2]} for c in cells],
        "data_version": dv,
    })

    # ---------- hotspots (page 1) ----------
    det_root = read_dataset(settings, "detections", [region])
    det_where = f"""latitude BETWEEN {s} AND {n} AND longitude BETWEEN {w} AND {e}"""
    total = con.execute(f"SELECT COUNT(*) FROM {det_root} WHERE {det_where}").fetchone()[0]
    rows = con.execute(f"""
        SELECT date_local, acq_datetime_utc, latitude, longitude,
               confidence_class, frp, daynight, sensor, platform, processing
        FROM {det_root} WHERE {det_where}
        ORDER BY acq_datetime_utc DESC LIMIT 100
    """).fetchall()
    write("hotspots.json", {
        "page": 1,
        "page_size": 100,
        "total": total,
        "rows": [{
            "date_local": str(r[0]),
            "acq_datetime_utc": str(r[1]),
            "latitude": r[2], "longitude": r[3],
            "confidence_class": r[4], "frp": r[5], "daynight": r[6],
            "sensor": r[7], "platform": r[8], "processing": r[9],
        } for r in rows],
        "data_version": dv,
    })

    # ---------- coverage ----------
    import json as _json
    cov_path = os.path.join(settings.DATA_PROCESSED, "coverage.json")
    regions = _json.load(open(cov_path)) if os.path.exists(cov_path) else []
    starter_areas = None
    import json as _json2
    regions_path = os.path.join("config", "regions.json")
    starter_areas = _json2.load(open(regions_path))["starter_areas"]
    write("coverage.json", {
        "regions": regions,
        "starter_areas": starter_areas,
        "data_version": dv,
    })

    # ---------- methods ----------
    val_path = os.path.join(settings.DATA_PROCESSED, "validation.json")
    validation = _json2.load(open(val_path)) if os.path.exists(val_path) else None
    cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
    cal_summary = None
    if os.path.exists(cal_path):
        kstats = con.execute(f"""
            SELECT platform, ROUND(MEDIAN(k), 4) AS k_median, COUNT(*) AS tiles
            FROM read_parquet('{cal_path}') WHERE level='tile_month' AND platform='Aqua'
            GROUP BY 1
        """).fetchall()
        cal_summary = [{"platform": r[0], "k_median": r[1], "tile_months": r[2]} for r in kstats]
    write("methods.json", {
        "region": region,
        "calibration": cal_summary,
        "validation": validation,
        "data_version": dv,
    })

    # ---------- health ----------
    write("health.json", {
        "status": "ok",
        "data_version": dv,
        "regions": [{"name": region, "latest_date": latest_s,
                     "age_days": (datetime.now().date() - latest).days}],
    })

    # ---------- example errors ----------
    write("error400.json", {"error": "invalid end date", "field": "end"})
    write("error422.json", {
        "error": "area is outside the covered regions",
        "covered_regions": ["southeast_asia"],
    })


if __name__ == "__main__":
    main()
