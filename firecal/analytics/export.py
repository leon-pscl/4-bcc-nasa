"""Export hotspot rows."""

import math

import duckdb
import pandas as pd

from firecal.analytics.area import Area
from firecal.config import Settings


def _area_sql(area, grid):
    if area.kind == "bbox":
        w, s, e, n = area.bbox
        return (
            f"(floor(latitude/{grid}) + 0.5) * {grid} >= {s} AND "
            f"(floor(latitude/{grid}) + 0.5) * {grid} < {n} AND "
            f"(floor(longitude/{grid}) + 0.5) * {grid} >= {w} AND "
            f"(floor(longitude/{grid}) + 0.5) * {grid} < {e}"
        ), []
    lat, lon, r = area.lat, area.lon, area.radius_km
    dlat = r / 111.0
    dlon = r / (111.0 * max(math.cos(math.radians(lat)), 1e-9))
    s, n = lat - dlat, lat + dlat
    w, e = lon - dlon, lon + dlon
    # haversine in SQL
    cond = (
        f"latitude BETWEEN {s} AND {n} AND longitude BETWEEN {w} AND {e} AND "
        f"(2*6371*asin(sqrt(sin(radians(latitude-{lat}))/2)^2 + cos(radians({lat}))*cos(radians(latitude))*sin(radians(longitude-{lon}))/2)^2)) <= {r}"
    )
    return cond, []


def hotspot_page(area: Area, start, end, page=1, page_size=100, all_sensors=False, settings=None):
    if settings is None:
        settings = Settings()
    det_path = f"{settings.DATA_PROCESSED}/detections.parquet"
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    grid = settings.GRID_DEG
    area_cond, _ = _area_sql(area, grid)
    conf = ",".join(f"'{c}'" for c in settings.CONFIDENCE_KEEP)
    type_cond = "type IS NULL OR type IN (" + ",".join(str(t) for t in settings.KEEP_TYPES) + ")"
    platform_cond = ""
    if not all_sensors:
        switch = settings.SWITCH_DATE
        platform_cond = f"AND ((platform='Aqua' AND date_local < DATE '{switch}') OR (platform='SNPP' AND date_local >= DATE '{switch}'))"
    base_where = (
        f"date_local BETWEEN DATE '{start_d}' AND DATE '{end_d}' "
        f"AND {area_cond} "
        f"AND confidence_class IN ({conf}) "
        f"AND ({type_cond}) "
        f"{platform_cond}"
    )
    con = duckdb.connect()
    total = con.execute(f"SELECT COUNT(*) FROM read_parquet('{det_path}') WHERE {base_where}").fetchone()[0]
    offset = (page - 1) * page_size
    cols = "date_local, acq_datetime_utc, latitude, longitude, confidence_class, frp, daynight, sensor, platform, processing"
    q = f"SELECT {cols} FROM read_parquet('{det_path}') WHERE {base_where} LIMIT {page_size} OFFSET {offset}"
    df = con.execute(q).df()
    con.close()
    return df, total


def hotspot_rows(area: Area, start, end, all_sensors=False, settings=None):
    if settings is None:
        settings = Settings()
    det_path = f"{settings.DATA_PROCESSED}/detections.parquet"
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    grid = settings.GRID_DEG
    area_cond, _ = _area_sql(area, grid)
    conf = ",".join(f"'{c}'" for c in settings.CONFIDENCE_KEEP)
    type_cond = "type IS NULL OR type IN (" + ",".join(str(t) for t in settings.KEEP_TYPES) + ")"
    platform_cond = ""
    if not all_sensors:
        switch = settings.SWITCH_DATE
        platform_cond = f"AND ((platform='Aqua' AND date_local < DATE '{switch}') OR (platform='SNPP' AND date_local >= DATE '{switch}'))"
    base_where = (
        f"date_local BETWEEN DATE '{start_d}' AND DATE '{end_d}' "
        f"AND {area_cond} "
        f"AND confidence_class IN ({conf}) "
        f"AND ({type_cond}) "
        f"{platform_cond}"
    )
    con = duckdb.connect()
    count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{det_path}') WHERE {base_where}").fetchone()[0]
    batch = 1000
    offset = 0
    cols = "date_local, acq_datetime_utc, latitude, longitude, confidence_class, frp, daynight, sensor, platform, processing"
    while offset < count:
        q = f"SELECT {cols} FROM read_parquet('{det_path}') WHERE {base_where} LIMIT {batch} OFFSET {offset}"
        df = con.execute(q).df()
        offset += batch
        if df.empty:
            break
        yield df
    con.close()