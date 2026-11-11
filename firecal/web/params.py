"""Parse query parameters into an Area + dates."""

from firecal.analytics.area import Area


def parse_area_and_dates(request):
    args = request.args
    if "bbox" in args:
        parts = args["bbox"].split(",")
        w, s, e, n = (float(x) for x in parts)
        area = Area.from_bbox(w, s, e, n)
    elif "point" in args:
        lat, lon = (float(x) for x in args["point"].split(","))
        radius = float(args.get("radius_km", 50))
        area = Area.from_point(lat, lon, radius)
    else:
        raise ValueError("missing area")
    start = args.get("start")
    end = args.get("end")
    if not start or not end:
        raise ValueError("missing dates")
    return area, start, end