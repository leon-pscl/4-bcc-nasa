"""Stage 5: Flask routes, all C6 endpoints."""

import csv
import io
import json
import os
import time
from datetime import date, datetime

import pandas as pd
from flask import jsonify, request, send_file, make_response

from firecal import analytics
from firecal.analytics.area import Area
from firecal.analytics.calendar import calendar_matrix
from firecal.analytics.export import hotspot_rows
from firecal.analytics.maps import map_cells
from firecal.analytics.summary import summary as _summary
from firecal.config import Settings
from firecal.dataset import DETECTIONS, HARMONIZED, CELLDAYS, data_version, load_state
from firecal.web.params import ParamError, CoverageError, latest_data_date, load_coverage, parse_query


def _app_version(settings):
    p = os.path.join(settings.DATA_PROCESSED, "data_version.json")
    try:
        return json.load(open(p)).get(HARMONIZED, "unknown")
    except Exception:
        return "unknown"


def _json_response(payload, status=200, etag=None):
    body = json.dumps(payload, separators=(",", ":")).encode()
    resp = make_response(body, status)
    resp.headers["Content-Type"] = "application/json"
    if etag:
        resp.headers["ETag"] = f'"{etag}"'
    return resp


def _cache_key(args, dv):
    return (tuple(sorted(args.items())), dv)


def create_app(settings=None):
    if settings is None:
        from firecal.config import Settings
        settings = Settings.from_env()
    from flask import Flask
    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    # in-process response cache, keyed on (path, args, data_version)
    cache = {}

    # ---------- helpers ----------
    def area_args():
        return parse_query(request.args.to_dict(), settings)

    def coverage_response():
        cov = load_coverage(settings)
        dv = _app_version(settings)
        regions = cov or []
        # enrich with label/countries from regions.json (C6 contract)
        regions_meta = {}
        rpath = os.path.join("config", "regions.json")
        if os.path.exists(rpath):
            for r in json.load(open(rpath)).get("regions", []):
                regions_meta[r["name"]] = r
        enriched = []
        for r in regions:
            meta = regions_meta.get(r.get("name"), {})
            enriched.append({
                "name": r.get("name"),
                "label": meta.get("label", r.get("label", r.get("name", ""))),
                "bbox": r.get("bbox"),
                "countries": meta.get("countries", r.get("countries", [])),
                "start": r.get("start"),
                "end": r.get("end") or r.get("latest_date"),
                "platforms": r.get("platforms", ["Aqua", "SNPP", "NOAA20", "NOAA21"]),
                "latest_date": r.get("latest_date"),
                "synthetic": bool(r.get("synthetic", False)),
            })
        regions = enriched
        # starter areas only for regions that have data
        region_names = {r["name"] for r in regions}
        starter_map = json.load(open(os.path.join("config", "regions.json")))["starter_areas"] \
            if os.path.exists(os.path.join("config", "regions.json")) else []
        starter = [s for s in starter_map if s.get("region") in region_names]
        for s in starter:
            match = next((r for r in regions if r.get("name") == s["region"]), None)
            if match and match.get("latest_date"):
                s["latest_date"] = match["latest_date"]
        return _json_response(
            {"regions": regions, "starter_areas": starter, "data_version": dv},
            etag=dv)

    def full_area(key):
        etag = _app_version(settings)
        cache_key = _cache_key(request.args.to_dict(), etag + key)
        if cache_key in cache:
            body, ct, status = cache[cache_key]
            resp = make_response(body, status)
            resp.headers["Content-Type"] = ct
            resp.headers["ETag"] = f'"{etag}"'
            return resp
        request.parent_cache_key = cache_key
        request.parent_etag = etag
        request.parent_cache = cache
        return None

    def store(resp):
        etag = _app_version(settings)
        cache_key = _cache_key(request.args.to_dict(), etag + request.endpoint)
        cache[cache_key] = (resp.get_data(), resp.headers.get("Content-Type", "application/json"), resp.status_code)
        return resp

    # ---------- static/frontend ----------
    @app.route("/")
    def index():
        dist = os.path.join("frontend", "dist")
        if os.path.exists(os.path.join(dist, "index.html")):
            return send_file(os.path.join(dist, "index.html"))
        return ("<p>frontend/dist not built. Run `npm run build` in frontend/ or use `npm run dev`.</p>", 200)

    @app.route("/assets/<path:p>")
    def assets(p):
        dist = os.path.join("frontend", "dist", "assets")
        return send_file(os.path.join(dist, p))

    @app.route("/health")
    def health():
        dv = _app_version(settings)
        cov = load_coverage(settings) or []
        today = date.today()
        regions = []
        stale = False
        for r in cov:
            try:
                latest = date.fromisoformat(r["latest_date"])
                age = (today - latest).days
            except Exception:
                age = None
            if age is not None and age > 3:
                stale = True
            regions.append({"name": r.get("name"), "latest_date": r.get("latest_date"), "age_days": age})
        status = "stale" if stale else "ok"
        return _json_response({"status": status, "data_version": dv, "regions": regions}, etag=dv)

    # ---------- API ----------
    @app.route("/api/coverage")
    def coverage():
        return coverage_response()

    @app.route("/api/calendar")
    def calendar():
        cached = full_area("calendar")
        if cached is not None:
            return cached
        area, start, end, today, region, coverage_warning = area_args()
        dv = request.parent_etag
        from firecal.analytics.calendar import calendar_matrix
        result = calendar_matrix(area, start, end, today, settings, region=region)
        query = {"start": start, "end": end, "area_km2": area.area_km2()}
        if area.radius_km is not None:
            query["point"] = [area.lat, area.lon]
            query["radius_km"] = area.radius_km
        else:
            query["bbox"] = [area.w, area.s, area.e, area.n]
        body = {
            "query": query,
            "unit": "Hotspots (harmonized)",
            "years": result["years"],
            "values": result["values"],
            "partial": result["partial"],
            "monthly_median": result["monthly_median"],
            "monthly_p25": result["monthly_p25"],
            "monthly_p75": result["monthly_p75"],
            "anomaly": result["anomaly"],
            "anomaly_pct": result["anomaly_pct"],
            "annual_totals": result["annual_totals"],
            "partial_years": result["partial_years"],
            "baseline_years": result["baseline_years"],
            "baseline_warning": result["baseline_warning"],
            "coverage_warning": result["coverage_warning"],
            "synthetic": False,
            "data_version": dv,
        }
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/summary")
    def summary():
        cached = full_area("summary")
        if cached is not None:
            return cached
        area, start, end, today, region, coverage_warning = area_args()
        dv = request.parent_etag
        result = _summary(area, start, end, today, settings, region=region)
        body = {**result, "synthetic": False, "data_version": dv}
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/map")
    def map():
        cached = full_area("map")
        if cached is not None:
            return cached
        area, start, end, today, region, coverage_warning = area_args()
        dv = request.parent_etag
        from firecal.analytics.maps import map_cells
        month = request.args.get("month")
        result = map_cells(area, start, end, settings, month=month, region=region)
        resp = _json_response({**result, "data_version": dv}, etag=dv)
        return store(resp)

    @app.route("/api/hotspots")
    def hotspots():
        dv = _app_version(settings)
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 100)), 1), 500)
        area, start, end, today, region, coverage_warning = area_args()
        all_sensors = request.args.get("all_sensors", "0") == "1"
        import duckdb
        con = duckdb.connect()
        con.execute("PRAGMA threads=2")
        root = __import__("firecal.dataset", fromlist=["read_dataset"]).read_dataset(
            settings, DETECTIONS, [region] if region else None)
        cl = area.bbox_sql(area)
        if area.radius_km is not None:
            cl = f"""
                6371000 * 2 * asin(sqrt(pow(sin(radians(latitude - {area.lat})/2), 2)
                  + cos(radians({area.lat})) * cos(radians(latitude))
                  * pow(sin(radians(longitude - {area.lon})/2), 2))) <= {area.radius_km * 1000}
            """
        else:
            cl = f"latitude BETWEEN {area.s} AND {area.n} AND longitude BETWEEN {area.w} AND {area.e}"
        if not all_sensors:
            # only detections that feed the harmonized series
            cl += " AND platform IN ('Aqua','SNPP','NOAA20','NOAA21')"
        total = con.execute(f"""
            SELECT COUNT(*) FROM {root}
            WHERE {cl} AND date_local >= DATE '{start}' AND date_local <= DATE '{end}'
        """).fetchone()[0]
        offset = (page - 1) * page_size
        rows_df = con.execute(f"""
            SELECT date_local, acq_datetime_utc, latitude, longitude,
                   confidence_class, frp, daynight, sensor, platform, processing
            FROM {root}
            WHERE {cl} AND date_local >= DATE '{start}' AND date_local <= DATE '{end}'
            ORDER BY acq_datetime_utc
            LIMIT {page_size} OFFSET {offset}
        """).df()
        if all_sensors:
            collumns = ["date_local", "acq_datetime_utc", "latitude", "longitude",
                        "confidence_class", "frp", "daynight", "sensor", "platform", "processing"]
            rows = [
                dict(zip(collumns, [
                    str(r[0]), str(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9],
                ]))
                for r in rows_df.itertuples(index=False, name=None)
            ]
        else:
            collumns = ["date_local", "acq_datetime_utc", "latitude", "longitude",
                        "confidence_class", "frp", "daynight"]
            rows = [
                dict(zip(collumns, [
                    str(r[0]), str(r[1]), r[2], r[3], r[4], r[5], r[6],
                ]))
                for r in rows_df.itertuples(index=False, name=None)
            ]
        body = {"page": page, "page_size": page_size, "total": total,
                "rows": rows, "data_version": dv}
        return _json_response(body, etag=dv)

    @app.route("/api/hotspots.csv")
    def hotspots_csv():
        area, start, end, today, region, coverage_warning = area_args()
        all_sensors = request.args.get("all_sensors", "0") == "1"
        from firecal.analytics.export import hotspots_csv as _hotspots_csv
        text = _hotspots_csv(area, start, end, settings, all_sensors=all_sensors, region=region)
        resp = make_response(text)
        resp.headers["Content-Type"] = "text/csv"
        w, s, e, n = (area.w, area.s, area.e, area.n) if area.radius_km is None else (area.lat, area.lon, area.radius_km, None)
        name = f"hotspots_{w}_{s}_{e}_{start}_{end}.csv"
        resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp

    @app.route("/api/calendar.csv")
    def calendar_csv():
        area, start, end, today, region, coverage_warning = area_args()
        result = calendar_matrix(area, start, end, today, settings, region=region)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["year", "month", "value"])
        for y, row in zip(result["years"], result["values"]):
            for m, v in enumerate(row, start=1):
                w.writerow([y, m, v if v is not None else ""])
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "text/csv"
        resp.headers["Content-Disposition"] = 'attachment; filename="calendar.csv"'
        return resp

    @app.route("/api/calendar.png")
    def calendar_png():
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        area, start, end, today, region, coverage_warning = area_args()
        result = calendar_matrix(area, start, end, today, settings, region=region)
        values = np.array([[v if v is not None else np.nan for v in row] for row in result["values"]], dtype=float)
        YlOrRd = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"]
        fig, ax = plt.subplots(figsize=(12, max(4, len(result["years"]) * 0.35)))
        im = ax.imshow(values, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("YlOrRd", YlOrRd))
        ax.set_xticks(range(12))
        ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        ax.set_yticks(range(len(result["years"])))
        ax.set_yticklabels(result["years"])
        for i in range(len(result["years"])):
            for j in range(12):
                v = values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6)
        fig.colorbar(im, ax=ax, label="Hotspots (harmonized)")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "image/png"
        return resp

    @app.route("/api/methods")
    def methods():
        region = request.args.get("region")
        if not region:
            return _json_response({"error": "missing region", "field": "region"}, status=400)
        dv = _app_version(settings)
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        if not os.path.exists(cal_path):
            return _json_response({"error": "region calibration not available", "field": "region"}, status=422)
        import duckdb
        con = duckdb.connect()
        con.execute("PRAGMA threads=2")
        krows = con.execute(f"""
            SELECT platform, k FROM read_parquet('{cal_path}')
            WHERE region = '{region}' AND level = 'tile_month' AND platform = 'Aqua'
        """).fetchall()
        if not krows:
            return _json_response({"error": "region not available", "field": "region"}, status=422)
        level_counts = dict(con.execute(f"""
            SELECT level, COUNT(*) FROM read_parquet('{cal_path}')
            WHERE region = '{region}' AND platform = 'Aqua' GROUP BY 1
        """).fetchall())
        val_path = os.path.join(settings.DATA_PROCESSED, "validation.json")
        validation = json.load(open(val_path)) if os.path.exists(val_path) else None
        import statistics
        ks = [r[1] for r in krows]
        calibration = {
            "k_median": float(statistics.median(ks)),
            "k_min": float(min(ks)),
            "k_max": float(max(ks)),
            "count_per_level": {str(k): int(v) for k, v in level_counts.items()},
        }
        body = {"region": region, "calibration": calibration,
                "validation": validation, "data_version": dv}
        return _json_response(body, etag=dv)

    # 304 for If-None-Match
    @app.before_request
    def _not_modified():
        dv = _app_version(settings)
        inm = request.headers.get("If-None-Match")
        if inm and inm.strip('"') == dv:
            resp = make_response("", 304)
            resp.headers["ETag"] = f'"{dv}"'
            resp.headers["Content-Type"] = "application/json"
            return resp

    @app.errorhandler(CoverageError)
    def _coverage_error(exc):
        return _json_response(
            {"error": str(exc), "covered_regions": getattr(exc, "covered_regions", [])},
            status=422)

    @app.errorhandler(ParamError)
    def _param_error(exc):
        body = {"error": str(exc)}
        if getattr(exc, "field", None):
            body["field"] = exc.field
        return _json_response(body, status=400)

    @app.errorhandler(Exception)
    def _unexpected(exc):
        return _json_response({"error": str(exc)}, status=500)

    return app