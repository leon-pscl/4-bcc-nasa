"""SQL helpers over Parquet (the only place that builds SQL)."""

import math


def area_where(area, grid, params):
    # returns (sql_fragment, params_list)
    if area.kind == "bbox":
        w, s, e, n = area.bbox
        frag = (
            "(cell_lat_idx + 0.5) * ? >= ? AND (cell_lat_idx + 0.5) * ? < ? AND "
            "(cell_lon_idx + 0.5) * ? >= ? AND (cell_lon_idx + 0.5) * ? < ?"
        )
        params.extend([grid, s, grid, n, grid, w, grid, e])
        return frag, params
    # point
    lat, lon, r = area.lat, area.lon, area.radius_km
    # bounding box in degrees
    dlat = r / 111.0
    dlon = r / (111.0 * max(math.cos(math.radians(lat)), 1e-9))
    s, n = lat - dlat, lat + dlat
    w, e = lon - dlon, lon + dlon
    frag = (
        "(cell_lat_idx + 0.5) * ? >= ? AND (cell_lat_idx + 0.5) * ? <= ? AND "
        "(cell_lon_idx + 0.5) * ? >= ? AND (cell_lon_idx + 0.5) * ? <= ?"
    )
    params.extend([grid, s, grid, n, grid, w, grid, e])
    return frag, params