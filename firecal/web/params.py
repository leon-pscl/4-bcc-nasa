"""Parse and validate area + date query parameters (Stage 5).

`today` is the latest data date (from coverage.json), never the server clock.
An `end` later than the latest data date is a 400 on `end`. An area outside
every covered region is a 422 with the coverage list.
"""

import json
import math
import os
from datetime import date


class ParamError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


class CoverageError(ParamError):
    def __init__(self, message, covered_regions):
        super().__init__(message)
        self.covered_regions = covered_regions


from firecal.analytics.area import Area
from firecal.dataset import read_dataset


def load_coverage(settings):
    p = os.path.join(settings.DATA_PROCESSED, "coverage.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


def latest_data_date(settings, region=None):
    """Latest complete local day in the coverage data.

    With `region`, the latest date of that region's coverage entry;
    otherwise the newest across all loaded regions (or the harmonized dataset).
    """
    cov = load_coverage(settings)
    if region is not None:
        for entry in cov:
            if entry.get("name") == region and entry.get("latest_date"):
                return entry["latest_date"]
    for entry in cov:
        if entry.get("latest_date"):
            return max(e["latest_date"] for e in cov if e.get("latest_date"))
    import duckdb
    con = duckdb.connect()
    try:
        root = read_dataset(settings, "harmonized_daily", [region] if region else None)
        row = con.execute(f"SELECT MAX(date_local) FROM {root}").fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        con.close()


def parse_bbox(value):
    parts = value.split(",")
    if len(parts) != 4:
        raise ParamError("bbox must be four numbers: W,S,E,N", "bbox")
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise ParamError("bbox must be four numbers: W,S,E,N", "bbox")


def _area_bbox(area):
    if area.radius_km is not None:
        dlat = area.radius_km / 111.0
        cos_lat = max(0.01, abs(math.cos(math.radians(area.lat))))
        dlon = area.radius_km / (111.0 * cos_lat)
        return area.lon - dlon, area.lat - dlat, area.lon + dlon, area.lat + dlat
    return area.w, area.s, area.e, area.n


def _coverage_status(area, regions):
    """Returns (region, warning, ok) for a parsed area."""
    aw, as_, ae, an = _area_bbox(area)
    full = []
    partial = []
    for name, bbox in regions:
        w, s, e, n = bbox
        ix = min(ae, e) - max(aw, w)
        iy = min(an, n) - max(as_, s)
        if ix > 0 and iy > 0:
            if aw >= w and ae <= e and as_ >= s and an <= n:
                full.append(name)
            else:
                partial.append(name)
    if full:
        return full[0], None, True
    if partial:
        return partial[0], "area only partly covered by regions: " + ", ".join(partial), True
    return None, None, False


def parse_query(args, settings):
    """Returns (Area, start, end, today, region, coverage_warning)."""
    bbox = args.get("bbox")
    point = args.get("point")
    radius = args.get("radius_km")
    start = args.get("start")
    end = args.get("end")
    if not start:
        raise ParamError("missing start", "start")
    if not end:
        raise ParamError("missing end", "end")
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except ValueError:
        raise ParamError("start/end must be YYYY-MM-DD", "start")
    if start_d > end_d:
        raise ParamError("start is after end", "start")

    if bbox:
        w, s, e, n = parse_bbox(bbox)
        try:
            area = Area.from_bbox(w, s, e, n, grid_deg=settings.GRID_DEG,
                                  max_area_km2=settings.MAX_AREA_KM2)
        except ValueError as exc:
            raise ParamError(str(exc), "bbox")
    elif point:
        try:
            lat, lon = (float(x) for x in point.split(","))
        except ValueError:
            raise ParamError("point must be LAT,LON", "point")
        if radius is None:
            raise ParamError("point requires radius_km", "radius_km")
        try:
            area = Area.from_point(lat, lon, float(radius), grid_deg=settings.GRID_DEG)
        except ValueError as exc:
            raise ParamError(str(exc), "radius_km")
    else:
        raise ParamError("provide bbox=W,S,E,N or point=LAT,LON&radius_km=R", "bbox")

    # coverage check (per-region: `today` and the end check use that region's latest date)
    cov = load_coverage(settings)
    regions = [(r.get("name"), r.get("bbox")) for r in cov if r.get("bbox")]
    region, warning, ok = _coverage_status(area, regions)
    if not ok:
        raise CoverageError("area is outside the covered regions", [r for r, _ in regions])
    latest = latest_data_date(settings, region)
    if latest and end_d > date.fromisoformat(latest):
        raise ParamError(f"end {end} is later than the latest data date {latest}", "end")
    return area, str(start_d), str(end_d), (latest or str(end_d)), region, warning
