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
from firecal.web.params import ParamError, CoverageError, load_coverage, parse_query, parse_area


def _app_version(settings):
    p = os.path.join(settings.DATA_PROCESSED, "data_version.json")
    try:
        return json.load(open(p)).get(HARMONIZED, "unknown")
    except Exception:
        return "unknown"


def _probe_harmonized(settings):
    """Open one harmonized partition (latest year, first file). (ok, detail)."""
    try:
        from pathlib import Path
        from firecal.duck import connect
        from firecal.dataset import processed_root
        root = Path(processed_root(settings)) / "harmonized_daily"
        cand = [str(p) for p in root.rglob("*.parquet")]
        if not cand:
            return False, f"no harmonized partitions found in {root}"
        def _y(p):
            try:
                return int(os.path.basename(os.path.dirname(p)).split("=")[1])
            except Exception:
                return -1
        cand.sort(key=lambda p: (_y(p), p))
        pick = cand[-1]
        con = connect(settings, "web")
        try:
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
    resp.headers["Cache-Control"] = "max-age=3600"
    return resp


def _cache_key(args, dv):
    return (tuple(sorted(args.items())), dv)


_ensure_data_status = {}


def _ensure_data(settings):
    """Ensure harmonized partitions exist; auto-download/extract to /tmp if needed."""
    global _ensure_data_status
    try:
        from pathlib import Path
        import shutil
        import urllib.request
        import zipfile
        from firecal.dataset import processed_root

        # 1. First check: does current DATA_PROCESSED have harmonized partitions?
        root = processed_root(settings)
        cand = list(root.rglob("data_0.parquet"))
        if cand:
            _ensure_data_status = {"ok": True, "count": len(cand), "path": str(root)}
            return True

        # 2. Fallback for a read-only app folder: clean dedicated dir in /tmp.
        target_dir = Path("/tmp/firecal_data") if os.name != "nt" else Path("data/processed")
        target_dir.mkdir(parents=True, exist_ok=True)
        cand = list(target_dir.rglob("data_0.parquet"))
        if not cand and settings.DATA_ZIP_URL:
            # Download the release archive and extract into target_dir,
            # normalizing any Windows backslashes in the entry names.
            dl_path = Path("/tmp/official_processed_data.zip") if os.name != "nt" else Path("temp_data.zip")
            req = urllib.request.Request(settings.DATA_ZIP_URL, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req) as resp, open(dl_path, "wb") as out:
                shutil.copyfileobj(resp, out)
            shutil.rmtree(str(target_dir), ignore_errors=True)
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dl_path, "r") as z:
                for member in z.infolist():
                    clean_name = member.filename.replace("\\", "/").strip("/")
                    if not clean_name or ".." in clean_name.split("/"):
                        continue
                    target_path = target_dir / clean_name
                    if member.is_dir() or member.filename.endswith("/") or member.filename.endswith("\\"):
                        target_path.mkdir(parents=True, exist_ok=True)
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)

        cand = list(target_dir.rglob("data_0.parquet"))

        # 3. Find the directory containing harmonized_daily
        if cand:
            # Find the root that contains harmonized_daily
            for p in cand:
                parts = p.parts
                if "harmonized_daily" in parts:
                    idx = parts.index("harmonized_daily")
                    resolved_data_dir = Path(*parts[:idx])
                    settings.DATA_PROCESSED = str(resolved_data_dir)
                    break
            _ensure_data_status = {
                "ok": True,
                "count": len(cand),
                "path": settings.DATA_PROCESSED,
                "sample": str(cand[0])
            }
            return True
        else:
            all_found = [str(p) for p in target_dir.rglob("*")][:15]
            _ensure_data_status = {
                "ok": False,
                "error": "0 parquet files found in target_dir",
                "path": str(target_dir),
                "contents": all_found
            }
            return False
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ensure_data error: %s", exc)
        _ensure_data_status = {"ok": False, "error": str(exc)}
        return False


def create_app(settings=None, dist_dir=None):
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if dist_dir is None:
        dist_dir = os.path.join(_repo_root, "frontend", "dist")
    if settings is None:
        from firecal.config import Settings
        settings = Settings.from_env()
    _ensure_data(settings)
    from flask import Flask
    app = Flask(__name__)
    app.debug = os.environ.get("FLASK_DEBUG", "0") == "1"  # default off; never the network debugger
    app.config["SETTINGS"] = settings

    # in-process response cache, keyed on (path, args, data_version); bounded LRU by bytes
    cache = OrderedDict()
    cache_limit_bytes = int(getattr(settings, "API_CACHE_MB", 32) or 32) * 1024 * 1024
    cache_bytes = 0

    def _cache_size(value):
        body, ct, _ = value
        return len(body) + len(ct or "") + 64

    def cache_put(key, value):
        nonlocal cache_bytes
        old = cache.pop(key, None)
        if old is not None:
            cache_bytes -= _cache_size(old)
        cache[key] = value
        cache_bytes += _cache_size(value)
        while cache and cache_bytes > cache_limit_bytes:
            _, evicted = cache.popitem(last=False)
            cache_bytes -= _cache_size(evicted)

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
        from firecal.outlook.api import outlook_version
        dv = f"{_app_version(settings)}-{outlook_version(settings)}"
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
        # outlook issue per region (if the outlook tables exist)
        from firecal.outlook.api import issued_targets
        from firecal.duck import connect
        for r in regions:
            name = r.get("name")
            try:
                con = connect(settings, "web")
                try:
                    issued, targets = issued_targets(con, settings, name)
                finally:
                    con.close()
            except Exception:
                issued, targets = None, []
            if issued:
                r["outlook"] = {"issued": issued,
                                "targets": [f"{y}-{m:02d}" for _, y, m in targets]}
        return _json_response(
            {"regions": regions, "starter_areas": starter, "data_version": dv},
            etag=dv)

    def full_area(key):
        etag = _app_version(settings)
        args = request.args.to_dict()
        start = args.get("start")
        end = args.get("end")
        cover = args.get("cover", "all")
        cr = None
        try:
            from firecal.web.params import parse_area, area_cell_range
            area, _region, _warn = parse_area(args, settings)
            cr = area_cell_range(area)
        except Exception:
            pass
        cache_key = (key, cr, start, end, cover, etag)
        hit = cache_get(cache_key)
        if hit is not None:
            body, ct, status = hit
            resp = make_response(body, status)
            resp.headers["Content-Type"] = ct
            resp.headers["ETag"] = f'"{etag}"'
            resp.headers["Cache-Control"] = "max-age=3600"
            return resp
        request.parent_cache_key = cache_key
        request.parent_etag = etag
        return None

    def store(resp):
        cache_key = getattr(request, "parent_cache_key", None)
        if cache_key is None:
            etag = _app_version(settings)
            args = request.args.to_dict()
            start = args.get("start")
            end = args.get("end")
            cover = args.get("cover", "all")
            cr = None
            try:
                from firecal.web.params import parse_area, area_cell_range
                area, _region, _warn = parse_area(args, settings)
                cr = area_cell_range(area)
            except Exception:
                pass
            cache_key = (request.endpoint, cr, start, end, cover, etag)
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

    @app.route("/mock/<path:p>")
    def mock(p):
        from flask import send_from_directory
        mock_dir = os.path.join(dist_dir, "mock")
        if not os.path.exists(mock_dir):
            mock_dir = os.path.join(_repo_root, "frontend", "public", "mock")
        return send_from_directory(mock_dir, p)

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
            body = {"status": status, "data_version": dv, "regions": regions, "ensure_status": _ensure_data_status}
        else:
            status = "error"
            body = {"status": status, "data_version": dv, "regions": regions,
                    "error": detail, "ensure_status": _ensure_data_status}
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
        focus_year = None
        if month_raw is not None:
            if "-" in month_raw:
                try:
                    parts = month_raw.split("-")
                    focus_year = int(parts[0])
                    month = int(parts[1])
                    if not (1 <= month <= 12):
                        raise ValueError
                except Exception:
                    return _json_response({"error": "month must be an integer 1-12", "field": "month"}, status=400)
            else:
                try:
                    month = int(month_raw)
                    if not (1 <= month <= 12):
                        raise ValueError
                except ValueError:
                    return _json_response({"error": "month must be an integer 1-12", "field": "month"}, status=400)
        result = map_cells(area, start, end, settings, month=month, year=focus_year, region=region, cover=cover)
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
        from firecal.analytics.cover import cover_exists_latlon
        from firecal.analytics.export import (_series_days_relation, _area_where,
                                              _source_filters)
        from firecal.dataset import dataset_dir
        if not dataset_dir(settings, DETECTIONS).exists():
            body = {"page": page, "page_size": page_size, "total": 0,
                    "rows": [], "data_version": dv,
                    "rows_note": "Detections not available in this deployment.",
                    "query": query_block(area, start, end, cover)}
            return _json_response(body, etag=dv)
        from firecal.duck import connect
        con = connect(settings, "web")
        try:
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
            # data span for rows_note (computed while con is open)
            try:
                mn, mx = con.execute(f"SELECT MIN(date_local), MAX(date_local) FROM {root} AS d").fetchone()
                request._data_min = str(mn)[:10] if mn is not None else None
                request._data_max = str(mx)[:10] if mx is not None else None
            except Exception:
                request._data_min = request._data_max = None
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
        rows_note = None
        mn = getattr(request, "_data_min", None)
        mx = getattr(request, "_data_max", None)
        if mn is not None and (start < mn or end > mx):
            rows_note = f"Hotspots are available from {mn} to {mx} only."
        body = {"page": page, "page_size": page_size, "total": total,
                "rows": rows, "data_version": dv,
                "rows_note": rows_note,
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
        from firecal.duck import connect
        con = connect(settings, "web")
        try:
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
        finally:
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
        from firecal.outlook.api import mask_stats, skill_numbers, issued_targets
        from firecal.duck import connect as _connect2
        outlook_info = None
        if os.path.exists(os.path.join(settings.DATA_PROCESSED, "monthly_cells.meta.json")):
            con2 = _connect2(settings, "web")
            try:
                issued, targets = issued_targets(con2, settings, region)
            finally:
                con2.close()
            ms = mask_stats(settings, region)
            grid = {"cells": ms["cells"],
                    "masked_share_of_fire_pct": ms["masked_share_of_fire_pct"]}
            outlook_info = {
                "grid_deg": settings.OUTLOOK_GRID_DEG,
                "mask": {"nonburnable_classes": list(settings.MASK_NONBURNABLE_CLASSES),
                          "min_burnable_pct": settings.MASK_MIN_BURNABLE_PCT},
                "threshold": settings.OUTLOOK_FIRE_THRESHOLD,
                "p_fire_rule": ("VIIRS years only (complete years >= 2013); "
                                "means and medians use the full record from 2003"),
                "model": "climatology",
                "issued": issued,
                "targets": [f"{y}-{m:02d}" for _, y, m in targets],
                "skill": skill_numbers(settings, region),
            }
        else:
            grid = None
        body = {"region": region, "calibration": calibration,
                "validation": validation, "data_version": dv}
        if grid is not None:
            body["grid"] = grid
        if outlook_info is not None:
            body["outlook"] = outlook_info
        return _json_response(body, etag=dv)

    def _outlook_query():
        cover = request.args.get("cover", "all")
        if cover != "all":
            raise ParamError("the outlook endpoints only take cover=all", "cover")
        area, region, warning = parse_area(request.args.to_dict(), settings)
        return area, region, warning

    def _outlook_dv():
        from firecal.outlook.api import outlook_version
        return outlook_version(settings)

    @app.route("/api/outlook")
    def outlook():
        cached = full_area("outlook")
        if cached is not None:
            return cached
        area, region, warning = _outlook_query()
        dv = _outlook_dv()
        from firecal.outlook.api import (area_cells, area_month_totals, issued_targets,
                                          outlook_lead_totals, area_single_month_total,
                                          top_cells, season_block, month_p25_p75,
                                          month_mean_median, skill_numbers)
        from firecal.outlook.monthly import _latest_date, _partial_month
        from firecal.outlook.climatology import complete_baseline_last, SERIES_START
        from firecal.duck import connect
        latest = _latest_date(settings, region)
        cells = area_cells(settings, region, area)
        con = connect(settings, "web")
        try:
            issued, targets = issued_targets(con, settings, region)
            if not issued:
                return _json_response({"error": "no outlook issued for this region yet",
                                       "field": "outlook"}, status=422)
            base_last = complete_baseline_last(settings, latest)
            totals = area_month_totals(con, settings, region, cells, SERIES_START, base_last)
            lead_totals = {int(lead): (int(ty), int(tm), float(exp or 0.0), int(likely or 0))
                           for lead, ty, tm, exp, likely in
                           outlook_lead_totals(con, settings, region, cells, issued)}
            partial = _partial_month(latest)
            months = []
            for lead, ty, tm in [(t[0], t[1], t[2]) for t in targets]:
                lt = lead_totals.get(lead)
                expected = lt[2] if lt else 0.0
                likely = lt[3] if lt else 0
                rng = month_p25_p75(totals, tm)
                nmean, nmedian = month_mean_median(totals, tm)
                so_far = None
                if partial and partial["year"] == ty and partial["month"] == tm:
                    v = area_single_month_total(con, settings, region, cells, ty, tm)
                    so_far = {"through_day": partial["through_day"], "value": v}
                months.append({"year": ty, "month": tm, "lead": lead, "model": "climatology",
                               "expected": round(expected, 1),
                               "typical_range": rng,
                               "normal_mean": nmean, "normal_median": nmedian,
                               "observed_so_far": so_far,
                               "cells_likely": likely})
            tops = top_cells(con, settings, region, cells, issued, per_lead=10)
        finally:
            con.close()
        skill = skill_numbers(settings, region)
        query = {"area_km2": round(area.area_km2(), 1)}
        if area.radius_km is not None:
            query["point"] = [area.lat, area.lon]
            query["radius_km"] = area.radius_km
        else:
            query["bbox"] = [area.w, area.s, area.e, area.n]
        body = {"query": query,
                "issued": issued, "latest_data_date": str(latest),
                "unit": "Hotspots (harmonized)", "grid_deg": settings.OUTLOOK_GRID_DEG,
                "threshold": settings.OUTLOOK_FIRE_THRESHOLD,
                "months": months,
                "top_cells": tops,
                "season": season_block(totals),
                "skill": skill,
                "data_version": dv, "synthetic": False,
                "coverage_warning": warning}
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/outlook/map")
    def outlook_map():
        cached = full_area("outlook-map")
        if cached is not None:
            return cached
        area, region, warning = _outlook_query()
        dv = _outlook_dv()
        lead_raw = request.args.get("lead", "1")
        try:
            lead = int(lead_raw)
            if not (1 <= lead <= settings.OUTLOOK_LEADS):
                raise ValueError
        except ValueError:
            return _json_response({"error": "lead must be an integer 1-3", "field": "lead"},
                                  status=400)
        from firecal.outlook.api import area_cells, issued_targets, map_cells
        from firecal.duck import connect
        cells = area_cells(settings, region, area)
        con = connect(settings, "web")
        try:
            issued, targets = issued_targets(con, settings, region)
            if not issued:
                return _json_response({"error": "no outlook issued for this region yet",
                                       "field": "outlook"}, status=422)
            target = next((t for t in targets if t[0] == lead), None)
            typ = _json_response({"error": "lead not available", "field": "lead"}, status=422)
            if target is None:
                return typ
            cells_out = map_cells(con, settings, region, cells, issued, lead)
        finally:
            con.close()
        body = {"grid_deg": settings.OUTLOOK_GRID_DEG, "issued": issued,
                "target": {"year": target[1], "month": target[2]},
                "model": "climatology",
                "cells": cells_out,
                "data_version": dv}
        resp = _json_response(body, etag=dv)
        return store(resp)

    @app.route("/api/outlook.csv")
    def outlook_csv():
        area, region, warning = _outlook_query()
        from firecal.outlook.api import area_cells, _outlook_root, issued_csv_rows
        from firecal.duck import connect
        cells = area_cells(settings, region, area)
        con = connect(settings, "web")
        try:
            rows = issued_csv_rows(con, settings, region, cells)
        finally:
            con.close()
        from firecal.outlook.grid import g_center
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["issued", "lead", "target_year", "target_month", "lat", "lon",
                    "p_fire", "p_fire_clim", "expected", "mean_clim", "model"])
        for issued, lead, ty, tm, la, lo, p, pc, e, m_, model in rows:
            w.writerow([issued, lead, ty, tm, round(g_center(la), 4), round(g_center(lo), 4),
                        round(float(p), 4), round(float(pc), 4), round(float(e), 4),
                        round(float(m_), 4), model])
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "text/csv"
        resp.headers["Content-Disposition"] = 'attachment; filename="outlook.csv"'
        return resp

    def _cells_area_range(args):
        start = args.get("start")
        end = args.get("end")
        if not start or not end:
            raise ParamError("missing start or end", "start" if not start else "end")
        for label, raw in (("start", start), ("end", end)):
            try:
                date.fromisoformat(raw)
            except ValueError:
                raise ParamError("start/end must be YYYY-MM-DD", label)
        return start, end

    @app.route("/api/cells.csv")
    def cells_csv():
        area, region, warning = _outlook_query()
        start, end = _cells_area_range(request.args.to_dict())
        from firecal.outlook.api import area_cells, cells_rows
        from firecal.duck import connect
        cells = area_cells(settings, region, area)
        con = connect(settings, "web")
        try:
            rows = cells_rows(con, settings, region, cells, start, end)
        except ValueError as exc:
            con.close()
            return _json_response({"error": str(exc), "field": "area"}, status=400)
        finally:
            con.close()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["year", "month", "lat", "lon", "value", "value_forest",
                    "value_farmland", "value_other", "fine_celldays"])
        for r in rows:
            w.writerow(r)
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "text/csv"
        if area.radius_km is not None:
            base = f"cells_point_{area.lat}_{area.lon}_{area.radius_km}_{start}_{end}"
        else:
            base = f"cells_{area.w}_{area.s}_{area.e}_{area.n}_{start}_{end}"
        resp.headers["Content-Disposition"] = f'attachment; filename="{base}.csv"'
        return resp

    @app.route("/api/cells.parquet")
    def cells_parquet():
        area, region, warning = _outlook_query()
        start, end = _cells_area_range(request.args.to_dict())
        from firecal.outlook.api import area_cells, cells_rows
        from firecal.duck import connect
        import pyarrow as pa
        import pyarrow.parquet as pq
        cells = area_cells(settings, region, area)
        con = connect(settings, "web")
        try:
            rows = cells_rows(con, settings, region, cells, start, end)
        except ValueError as exc:
            con.close()
            return _json_response({"error": str(exc), "field": "area"}, status=400)
        finally:
            con.close()
        table = pa.table({
            "year": [r[0] for r in rows],
            "month": [r[1] for r in rows],
            "lat": [r[2] for r in rows],
            "lon": [r[3] for r in rows],
            "value": [r[4] for r in rows],
            "value_forest": [r[5] for r in rows],
            "value_farmland": [r[6] for r in rows],
            "value_other": [r[7] for r in rows],
            "fine_celldays": [r[8] for r in rows],
        })
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "application/vnd.apache.parquet"
        if area.radius_km is not None:
            base = f"cells_point_{area.lat}_{area.lon}_{area.radius_km}_{start}_{end}"
        else:
            base = f"cells_{area.w}_{area.s}_{area.e}_{area.n}_{start}_{end}"
        resp.headers["Content-Disposition"] = f'attachment; filename="{base}.parquet"'
        return resp

    # 304 for If-None-Match
    @app.before_request
    def _not_modified():
        from firecal.outlook.api import outlook_version
        outlook_path = request.path.startswith(("/api/outlook", "/api/cells"))
        dv = outlook_version(settings) if outlook_path else _app_version(settings)
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

    # background warm-up: compute starter areas + outlook without blocking startup
    try:
        import threading, time, logging
        _log = logging.getLogger(__name__)
        def _warmup():
            time.sleep(1)
            t0 = time.time()
            try:
                client = app.test_client()
                from firecal.web.params import load_coverage
                cov = load_coverage(settings) or []
                region_latest = {}
                for r in cov:
                    if r.get("name") and r.get("latest_date"):
                        region_latest[r["name"]] = r["latest_date"]
                regions_meta = {}
                try:
                    regions_meta = {r["name"]: r for r in json.load(open(os.path.join("config", "regions.json"))).get("regions", [])}
                except Exception:
                    pass
                starter = []
                try:
                    starter = json.load(open(os.path.join("config", "regions.json"))).get("starter_areas", [])
                except Exception:
                    pass
                for s in starter:
                    region = s.get("region")
                    bbox = s.get("bbox")
                    if not bbox or not region:
                        continue
                    latest = region_latest.get(region)
                    if not latest:
                        continue
                    # start = first of latest year? use 2003-01-01 as default start
                    start = "2003-01-01"
                    end = latest
                    w, so, e, n = bbox
                    qs = f"bbox={w},{so},{e},{n}&start={start}&end={end}"
                    for cover in ("all", "forest", "farmland", "other"):
                        for ep in ("/api/calendar", "/api/summary", "/api/series", "/api/map", "/api/hotspots"):
                            try:
                                client.get(f"{ep}?{qs}&cover={cover}")
                            except Exception:
                                pass
                        # outlook (cover=all only)
                        try:
                            client.get(f"/api/outlook?bbox={w},{so},{e},{n}&start={start}&end={end}&cover=all")
                        except Exception:
                            pass
                _log.info("warm-up completed in %.1fs", time.time() - t0)
            except Exception as exc:
                _log.warning("warm-up failed: %s", exc)
        threading.Thread(target=_warmup, daemon=True).start()
    except Exception:
        pass

    return app
