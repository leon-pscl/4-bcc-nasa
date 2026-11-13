"""Export analytics (Stage 4): iterate over hotspot detections (paged)."""

import pandas as pd

from firecal.dataset import read_dataset


def hotspot_rows(area, start, end, settings, all_sensors=False, region=None,
                 batch_size=1000):
    """Yield DataFrames of detection rows in the area/date range, in batches."""
    import duckdb
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    root = read_dataset(settings, "detections", [region] if region else None)
    cell_filter = None
    if area.radius_km is not None:
        # haversine filter
        lat = area.lat
        lon = area.lon
        r = area.radius_km
        cell_filter = (f"haversine_distance_m? ", None)
        # fall back to bbox prefilter is not safe; use python haversine on batches
        lat_c = lat
    else:
        w, s, e, n = area.w, area.s, area.e, area.n
        cell_filter_sql = f"latitude BETWEEN {s} AND {n} AND longitude BETWEEN {w} AND {e}"
    sensor_filter = "" if all_sensors else ""
    offset = 0
    while True:
        if area.radius_km is not None:
            r_ = area.radius_km
            cl = f"""
                6371000 * 2 * asin(sqrt(pow(sin(radians(latitude - {area.lat})/2), 2)
                  + cos(radians({area.lat})) * cos(radians(latitude))
                  * pow(sin(radians(longitude - {area.lon})/2), 2))) <= {r_ * 1000}
            """
        else:
            cl = cell_filter_sql
        df = con.execute(f"""
            SELECT date_local, acq_datetime_utc, latitude, longitude,
                   confidence_class, frp, daynight, sensor, platform, processing
            FROM {root}
            WHERE {cl}
              AND date_local >= DATE '{start}' AND date_local <= DATE '{end}'
              {sensor_filter}
            ORDER BY acq_datetime_utc
            LIMIT {batch_size} OFFSET {offset}
        """).df()
        if not len(df):
            break
        yield df
        offset += batch_size


def hotspots_csv(area, start, end, settings, all_sensors=False, region=None):
    import io
    buf = io.StringIO()
    buf.write("date_local,acq_datetime_utc,latitude,longitude,confidence_class,frp,daynight,sensor,platform,processing\n")
    for df in hotspot_rows(area, start, end, settings, all_sensors=all_sensors, region=region):
        for _, r in df.iterrows():
            buf.write(f"{r.date_local},{r.acq_datetime_utc},{r.latitude},{r.longitude},{r.confidence_class},{r.frp},{r.daynight},{r.sensor},{r.platform},{r.processing}\n")
    return buf.getvalue()
