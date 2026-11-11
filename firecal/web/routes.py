"""Routes."""

import pandas as pd
from flask import jsonify, request, Response, stream_with_context

from firecal.web.params import parse_area_and_dates
from firecal.analytics import calendar as cal_mod, summary as sum_mod, maps as maps_mod, export as exp_mod
from firecal.config import Settings


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
            return jsonify({"error": str(e), "field": "area"}), 400
        data = cal_mod.calendar_matrix(area, start, end, settings=settings)
        return jsonify(data)

    @app.get("/api/summary")
    def summary():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            return jsonify({"error": str(e), "field": "area"}), 400
        from datetime import date
        data = sum_mod.summary(area, start, end, today=date.today(), settings=settings)
        return jsonify(data)

    @app.get("/api/map")
    def map_():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            return jsonify({"error": str(e), "field": "area"}), 400
        month = request.args.get("month")
        data = maps_mod.map_cells(area, start, end, month=month, settings=settings)
        return jsonify(data)

    @app.get("/api/hotspots")
    def hotspots():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            return jsonify({"error": str(e), "field": "area"}), 400
        page = int(request.args.get("page", 1))
        page_size = min(int(request.args.get("page_size", 100)), 500)
        chunks = list(exp_mod.hotspot_rows(area, start, end, all_sensors=request.args.get("all_sensors") == "1", settings=settings))
        df = pd.concat(chunks) if chunks else __import__("pandas").DataFrame()
        total = len(df)
        start_i = (page - 1) * page_size
        page_df = df.iloc[start_i:start_i + page_size]
        return jsonify({"page": page, "page_size": page_size, "total": total, "rows": page_df.to_dict("records")})

    @app.get("/api/hotspots.csv")
    def hotspots_csv():
        try:
            area, start, end = parse_area_and_dates(request)
        except Exception as e:
            return jsonify({"error": str(e), "field": "area"}), 400
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
            return jsonify({"error": str(e), "field": "area"}), 400
        data = cal_mod.calendar_matrix(area, start, end, settings=settings)
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["year"] + [f"m{m}" for m in range(1, 13)])
        for i, y in enumerate(data["years"]):
            w.writerow([y] + data["values"][i])
        return Response(buf.getvalue(), mimetype="text/csv")

    @app.get("/api/methods")
    def methods():
        import json
        from pathlib import Path
        p = Path(settings.DATA_PROCESSED) / "validation.json"
        v = json.loads(p.read_text()) if p.exists() else {}
        return jsonify({"calibration": "see calibration.parquet", "validation": v})

    @app.get("/api/calendar.png")
    def calendar_png():
        return Response("not implemented", status=501)