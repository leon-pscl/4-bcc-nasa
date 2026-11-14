"""Stage 5: Flask routes, all C6 endpoints."""

import csv
import io
import json
import os
import time
from collections import OrderedDict
from datetime import date, datetime

import pandas as pd
from flask import request, send_file, make_response
from werkzeug.exceptions import HTTPException

from firecal.analytics.calendar import calendar_matrix
from firecal.analytics.export import stream_hotspots_csv
from firecal.analytics.maps import map_cells
from firecal.analytics.summary import summary as _summary
from firecal.config import Settings
from firecal.dataset import DETECTIONS, HARMONIZED, read_dataset
from firecal.web.images import render_calendar_png
from firecal.web.params import ParamError, CoverageError, load_coverage, parse_query


def _app_version(settings):
    p = os.path.join(settings.DATA_PROCESSED, "data_version.json")
    try:
        return json.load(open(p)).get(HARMONIZED, "unknown")
    except Exception:
        return "unknown"


def _probe_harmonized(settings):
    """Open one harmonized partition (latest year, first file). (ok, detail)."""
    try:
        import glob
        import duckdb
        root = os.path.join(settings.DATA_PROCESSED, "harmonized_daily")
        cand = glob.glob(os.path.join(root, "region=*", "year=*", "*.parquet"))
        if not cand:
            return False, "no harmonized partitions found"
        def _y(p):
            try:
                return int(os.path.basename(os.path.dirname(p)).split("=")[1])
            except Exception:
                return -1
        cand.sort(key=lambda p: (_y(p), p))
        pick = cand[-1]
        rel = os.path.relpath(pick, settings.DATA_PROCESSED)
        con = duckdb.connect()
        try:
            con.execute("PRAGMA threads=1")
            con.execute("PRAGMA memory_limit='512MB'")
            con.execute(f"SELECT COUNT(*) FROM read_parquet('{pick.replace(os.sep, '/')}')").fetchone()
        finally:
            con.close()
        return True, None
    except Exception as e:
        return False, f"cannot read harmonized partition: {e}"


def _json_response(payload, status=200, etag=None):
    body = json.dumps(payload, separators=(",", ":")).encode()
    resp = make_response(body, status)
    resp.headers["Content-Type"] = "application/json"
    if etag:
        resp.headers["ETag"] = f'"{etag}"'
    return resp


def _cache_key(args, dv):
    return (tuple(sorted(args.items())), dv)


def create_app(settings=None, dist_dir=None):
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if dist_dir is None:
        dist_dir = os.path.join(_repo_root, "frontend", "dist")
    if settings is None:
        from firecal.config import Settings
        settings = Settings.from_env()
    from flask import Flask
    app = Flask(__name__)
    app.debug = os.environ.get("FLASK_DEBUG", "0") == "1"  # default off; never the network debugger
    app.config["SETTINGS"] = settings

    # in-process response cache, keyed on (path, args, data_version); bounded LRU
    cache = OrderedDict()
    cache_limit = int(getattr(settings, "API_CACHE_ENTRIES", 512) or 512)

    def cache_put(key, value):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > cache_limit:
            cache.popitem(last=False)

    def cache_get(key):
        value = cache.get(key)
        if value is not None:
            cache.move_to_end(key)
        return value

    # ---------- helpers ----------
    def area_args():
        return parse_query(request.args.to_dict(), settings)

    def cover_arg():
        cover = request.args.get("cover", "all")
        if cover not in ("all", "forest", "farmland", "other"):
            raise ParamError("cover must be one of all, forest, farmland, other", "cover")
        return cover

    def query_block(area, start, end, cover):
        q = {"start": str(start), "end": str(end), "area_km2": area.area_km2(), "cover": cover}
        if area.radius_km is not None:
            q["point"] = [area.lat, area.lon]
            q["radius_km"] = area.radius_km
        else:
            q["bbox"] = [area.w, area.s, area.e, area.n]
        return q

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
        hit = cache_get(cache_key)
        if hit is not None:
            body, ct, status = hit
            resp = make_response(body, status)
            resp.headers["Content-Type"] = ct
            resp.headers["ETag"] = f'"{etag}"'
            return resp
        request.parent_cache_key = cache_key
        request.parent_etag = etag
        return None

    def store(resp):
        etag = _app_version(settings)
        cache_key = _cache_key(request.args.to_dict(), etag + request.endpoint)
        cache_put(cache_key, (resp.get_data(), resp.headers.get("Content-Type", "application/json"), resp.status_code))
        return resp

    # ---------- static/frontend ----------
    def _today():
        raw = os.environ.get("FIRECAL_TODAY")
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return date.today()

    @app.route("/")
    def index():
        if os.path.exists(os.path.join(dist_dir, "index.html")):
            return send_file(os.path.join(dist_dir, "index.html"))
        return ("<p>frontend/dist not built. Run `npm run build` in frontend/ or use `npm run dev`.</p>", 200)

    @app.route("/assets/<path:p>")
    def assets(p):
        from flask import send_from_directory
        return send_from_directory(os.path.join(dist_dir, "assets"), p)

    @app.route("/health")
    def health():
        dv = _app_version(settings)
        cov = load_coverage(settings) or []
        today = _today()
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
        ok, detail = _probe_harmonized(settings)
        if ok:
            status = "stale" if stale else "ok"
            body = {"status": status, "data_version": dv, "regions": regions}
        else:
            status = "error"
            body = {"status": status, "data_version": dv, "regions": regions,
                    "error": detail}
        return _json_response(body, etag=dv)

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
        cover = cover_arg()
        from firecal.analytics.calendar import calendar_matrix
        result = calendar_matrix(area, start, end, today, settings, region=region, cover=cover)
        query = query_block(area, start, end, cover)
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
            "coverage_warning": coverage_warning,
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
        cover = cover_arg()
        result = _summary(area, start, end, today, settings, region=region, cover=cover)
        body = {**result, "synthetic": False, "data_version": dv,
                "coverage_warning": coverage_warning,
                "query": query_block(area, start, end, cover)}
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/series")
    def series():
        cached = full_area("series")
        if cached is not None:
            return cached
        area, start, end, today, region, coverage_warning = area_args()
        dv = request.parent_etag
        cover = cover_arg()
        from firecal.analytics.series import seam_series
        result = seam_series(area, start, end, settings, region=region, cover=cover)
        query = query_block(area, start, end, cover)
        body = {
            "query": query,
            **result,
            "latest_data_date": str(today),
            "synthetic": False,
            "coverage_warning": coverage_warning,
            "data_version": dv,
        }
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/map")
    def map():
        cached = full_area("map")
        if cached is not None:
            return cached
        area, start, end, today, region, coverage_warning = area_args()
        dv = request.parent_etag
        cover = cover_arg()
        import math
        month_raw = request.args.get("month")
        month = None
        if month_raw is not None:
            try:
                month = int(month_raw)
                if not (1 <= month <= 12):
                    raise ValueError
            except ValueError:
                return _json_response({"error": "month must be an integer 1-12", "field": "month"}, status=400)
        result = map_cells(area, start, end, settings, month=month, region=region, cover=cover)
        resp = _json_response({**result, "data_version": dv,
                               "coverage_warning": coverage_warning,
                               "query": query_block(area, start, end, cover)}, etag=dv)
        return store(resp)

    @app.route("/api/hotspots")
    def hotspots():
        dv = _app_version(settings)
        try:
            page = max(int(request.args.get("page", 1)), 1)
        except (TypeError, ValueError):
            return _json_response({"error": "page must be an integer >= 1", "field": "page"}, status=400)
        try:
            page_size = min(max(int(request.args.get("page_size", 100)), 1), 500)
        except (TypeError, ValueError):
            return _json_response({"error": "page_size must be an integer 1-500", "field": "page_size"}, status=400)
        area, start, end, today, region, coverage_warning = area_args()
        all_sensors = request.args.get("all_sensors", "0") == "1"
        cover = cover_arg()
        import duckdb
        from firecal.analytics.cover import cover_exists_latlon
        from firecal.analytics.export import (_series_days_relation, _area_where,
                                              _source_filters)
        con = duckdb.connect()
        try:
            con.execute("PRAGMA threads=2")
            root = read_dataset(settings, DETECTIONS, [region] if region else None)
            cl = _area_where(area)
            conf_sql, type_sql = _source_filters(settings)
            cover_pred = cover_exists_latlon(settings, cover, "d")
            series_join = ""
            if not all_sensors:
                # only detections that feed the harmonized series
                _series_days_relation(con, settings, region)
                series_join = ("JOIN series_days AS sd ON sd.region = d.region "
                               "AND sd.date_local = d.date_local AND d.platform = sd.platform")
            total = con.execute(f"""
                SELECT COUNT(*) FROM {root} AS d
                {series_join}
                WHERE {cl} AND d.date_local >= DATE '{start}' AND d.date_local <= DATE '{end}'
                  AND {conf_sql} AND {type_sql} AND ({cover_pred})
            """).fetchone()[0]
            offset = (page - 1) * page_size
            rows_df = con.execute(f"""
                SELECT d.date_local, d.acq_datetime_utc, d.latitude, d.longitude,
                       d.confidence_class, d.frp, d.daynight, d.sensor, d.platform, d.processing
                FROM {root} AS d
                {series_join}
                WHERE {cl} AND d.date_local >= DATE '{start}' AND d.date_local <= DATE '{end}'
                  AND {conf_sql} AND {type_sql} AND ({cover_pred})
                ORDER BY d.acq_datetime_utc
                LIMIT {page_size} OFFSET {offset}
            """).df()
        finally:
            con.close()
        columns = ["date_local", "acq_datetime_utc", "latitude", "longitude",
                   "confidence_class", "frp", "daynight", "sensor", "platform", "processing"]
        rows = [
            dict(zip(columns, [pd.to_datetime(r[0]).strftime("%Y-%m-%d"),
                               pd.to_datetime(r[1]).isoformat(),
                               r[2], r[3], r[4], r[5], r[6],
                               r[7], r[8], r[9]]))
            for r in rows_df.itertuples(index=False, name=None)
        ]
        body = {"page": page, "page_size": page_size, "total": total,
                "rows": rows, "data_version": dv,
                "query": query_block(area, start, end, cover)}
        return _json_response(body, etag=dv)

    @app.route("/api/hotspots.csv")
    def hotspots_csv():
        area, start, end, today, region, coverage_warning = area_args()
        all_sensors = request.args.get("all_sensors", "0") == "1"
        cover = cover_arg()
        from flask import Response, stream_with_context
        if area.radius_km is not None:
            base = f"hotspots_point_{area.lat}_{area.lon}_{area.radius_km}_{start}_{end}"
        else:
            base = f"hotspots_{area.w}_{area.s}_{area.e}_{area.n}_{start}_{end}"
        if cover != "all":
            base = base.replace("hotspots", f"hotspots_{cover}", 1)
        name = f"{base}.csv"
        return Response(
            stream_with_context(stream_hotspots_csv(area, start, end, settings,
                                                  all_sensors=all_sensors, region=region,
                                                  cover=cover)),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.route("/api/calendar.csv")
    def calendar_csv():
        area, start, end, today, region, coverage_warning = area_args()
        cover = cover_arg()
        result = calendar_matrix(area, start, end, today, settings, region=region, cover=cover)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["year", "month", "value"])
        for y, row in zip(result["years"], result["values"]):
            for m, v in enumerate(row, start=1):
                w.writerow([y, m, v if v is not None else ""])
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "text/csv"
        name = f"calendar_{cover}.csv" if cover != "all" else "calendar.csv"
        resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp

    @app.route("/api/calendar.png")
    def calendar_png():
        area, start, end, today, region, coverage_warning = area_args()
        cover = cover_arg()
        result = calendar_matrix(area, start, end, today, settings, region=region, cover=cover)
        png = render_calendar_png(result["years"], result["values"])
        resp = make_response(png)
        resp.headers["Content-Type"] = "image/png"
        name = f"calendar_{cover}.png" if cover != "all" else "calendar.png"
        resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp

    @app.route("/api/methods")
    def methods():
        region = request.args.get("region")
        if not region:
            return _json_response({"error": "missing region", "field": "region"}, status=400)
        # only region names from the coverage list are queryable (no SQL from input)
        names = {r.get("name") for r in (load_coverage(settings) or [])}
        if region not in names:
            return _json_response({"error": "unknown region", "field": "region"}, status=422)
        dv = _app_version(settings)
        cal_path = os.path.join(settings.DATA_PROCESSED, "calibration.parquet")
        if not os.path.exists(cal_path):
            return _json_response({"error": "region calibration not available", "field": "region"}, status=422)
        import duckdb
        con = duckdb.connect()
        con.execute("PRAGMA threads=2")
        krows = con.execute(
            "SELECT platform, k FROM read_parquet(?) "
            "WHERE region = ? AND level = 'tile_month' AND platform = 'Aqua'",
            [cal_path, region]).fetchall()
        if not krows:
            return _json_response({"error": "region not available", "field": "region"}, status=422)
        level_counts = dict(con.execute(
            "SELECT level, COUNT(*) FROM read_parquet(?) "
            "WHERE region = ? AND platform = 'Aqua' GROUP BY 1",
            [cal_path, region]).fetchall())
        con.close()
        # read the requested region's validation file (C5), falling back to the
        # legacy single validation.json for older data sets
        val_path = os.path.join(settings.DATA_PROCESSED, "validation", region + ".json")
        if not os.path.exists(val_path):
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

    @app.errorhandler(404)
    def _not_found(_):
        if request.path.startswith("/api/"):
            return _json_response({"error": "not found"}, status=404)
        index = os.path.join(dist_dir, "index.html")
        if os.path.exists(index):
            return send_file(index)
        return "not found", 404

    @app.errorhandler(HTTPException)
    def _http_exception(exc):
        return _json_response({"error": exc.description}, status=exc.code)

    @app.errorhandler(Exception)
    def _unexpected(exc):
        import logging
        logging.getLogger(__name__).exception("unexpected error: %s", exc)
        return _json_response({"error": "internal server error"}, status=500)

    return app