"""Routes."""

import pandas as pd
from flask import jsonify, request, Response, stream_with_context

from firecal.web.params import parse_area_and_dates
from firecal.analytics import calendar as cal_mod, summary as sum_mod, maps as maps_mod, export as exp_mod
import json
from pathlib import Path

from firecal.config import Settings


def _coverage_check(area, settings):
    p = Path(settings.DATA_PROCESSED) / "coverage.json"
    cov = json.loads(p.read_text()) if p.exists() else []
    if not cov:
        return False, None
    # outside all?
    outside = True
    partial = False
    for c in cov:
        w, s, e, n = c["bbox"]
        if area.kind == "bbox":
            aw, as_, ae, an = area.bbox
            # overlap?
            if not (e <= aw or w >= ae or n <= as_ or s >= an):
                outside = False
                # partial if area not fully inside coverage
                if not (w <= aw and e >= ae and s <= as_ and n >= an):
                    partial = True
        else:
            if w <= area.lon < e and s <= area.lat < n:
                outside = False
    if outside:
        return True, cov
    return False, ("area only partly overlaps coverage" if partial else None)


def register_routes(app, settings):
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/coverage")
    def coverage():
        import json
        from pathlib import Path
        p = Path(settings.DATA_PROCESSED) / "coverage.json"
        if not p.exists():
            return jsonify([])
        return jsonify(json.loads(p.read_text()))

    @app.get("/api/calendar")
    def calendar():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        outside, info = _coverage_check(area, settings)
        if outside:
            return jsonify({"error": "no coverage", "coverage": info}), 422
        data = cal_mod.calendar_matrix(area, start, end, settings=settings)
        if info:
            data["coverage_warning"] = info
        return jsonify(data)

    @app.get("/api/summary")
    def summary():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        from datetime import date
        data = sum_mod.summary(area, start, end, today=date.today(), settings=settings)
        return jsonify(data)

    @app.get("/api/map")
    def map_():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        month = request.args.get("month")
        data = maps_mod.map_cells(area, start, end, month=month, settings=settings)
        return jsonify(data)

    @app.get("/api/hotspots")
    def hotspots():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        page = int(request.args.get("page", 1))
        page_size = min(int(request.args.get("page_size", 100)), 500)
        df, total = exp_mod.hotspot_page(area, start, end, page=page, page_size=page_size, all_sensors=request.args.get("all_sensors") == "1", settings=settings)
        return jsonify({"page": page, "page_size": page_size, "total": total, "rows": df.to_dict("records")})

    @app.get("/api/hotspots.csv")
    def hotspots_csv():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        all_s = request.args.get("all_sensors") == "1"
        gen = exp_mod.hotspot_rows(area, start, end, all_sensors=all_s, settings=settings)

        def stream():
            first = True
            for chunk in gen:
                if first:
                    yield chunk.to_csv(index=False)
                    first = False
                else:
                    yield chunk.to_csv(index=False, header=False)

        filename = f"hotspots_{area.bbox[0]}_{area.bbox[1]}_{area.bbox[2]}_{area.bbox[3]}_{start}_{end}.csv" if area.kind == "bbox" else "hotspots.csv"
        return Response(stream_with_context(stream()), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.get("/api/calendar.csv")
    def calendar_csv():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        data = cal_mod.calendar_matrix(area, start, end, settings=settings)
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["year"] + [f"m{m}" for m in range(1, 13)])
        for i, y in enumerate(data["years"]):
            w.writerow([y] + [("" if v is None else v) for v in data["values"][i]])
        filename = f"calendar_{start}_{end}.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.get("/api/methods")
    def methods():
        import json
        from pathlib import Path
        import pandas as pd
        p = Path(settings.DATA_PROCESSED) / "validation.json"
        v = json.loads(p.read_text()) if p.exists() else {}
        cal_path = Path(settings.DATA_PROCESSED) / "calibration.parquet"
        summary = {}
        if cal_path.exists():
            cal = pd.read_parquet(cal_path)
            summary = {
                "count_per_level": cal["level"].value_counts().to_dict(),
                "k_min": float(cal["k"].min()),
                "k_median": float(cal["k"].median()),
                "k_max": float(cal["k"].max()),
            }
        return jsonify({"calibration": summary, "validation": v})

    @app.get("/api/calendar.png")
    def calendar_png():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            field = str(e) if str(e) in ("bbox", "point", "radius_km", "start", "end") else "area"
            return jsonify({"error": str(e), "field": field}), 400
        from firecal.web.images import render_calendar_png
        img = render_calendar_png(area, start, end, settings=settings)
        return Response(img, mimetype="image/png")