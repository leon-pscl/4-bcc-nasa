"""Parse query parameters into an Area + dates."""

from datetime import date

from firecal.analytics.area import Area


def parse_area_and_dates(request):
    args = request.args
    # area
    if "bbox" in args:
        try:
            parts = args["bbox"].split(",")
            if len(parts) != 4:
                raise ValueError("bbox")
            w, s, e, n = (float(x) for x in parts)
            area = Area.from_bbox(w, s, e, n)
        except ValueError:
            raise ValueError("bbox")
    elif "point" in args:
        try:
            lat, lon = (float(x) for x in args["point"].split(","))
        except ValueError:
            raise ValueError("point")
        if "radius_km" not in args:
            raise ValueError("radius_km")
        try:
            radius = float(args["radius_km"])
        except ValueError:
            raise ValueError("radius_km")
        try:
            area = Area.from_point(lat, lon, radius)
        except ValueError:
            raise ValueError("radius_km")
    else:
        raise ValueError("bbox")

    start = args.get("start")
    end = args.get("end")
    if not start:
        raise ValueError("start")
    if not end:
        raise ValueError("end")
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except ValueError:
        raise ValueError("start")
    if start_d > end_d:
        raise ValueError("start")
    if end_d > date.today():
        raise ValueError("end")
    # attach parsed dates? return strings
    return area, start, end