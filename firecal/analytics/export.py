"""Export analytics (Stage 4): paged hotspot rows, streamed from one query.

By default only the detections that feed the harmonized series for each date are
exported (the series_days table: Aqua before the switch date; after it, SNPP,
else NOAA-20, else NOAA-21, else Aqua). all_sensors=True drops that selection and
exports every detection, keeping the source filters (settings.CONFIDENCE_KEEP
and settings.KEEP_TYPES). Rows stream in 8k-row chunks from one query.
"""

import io
import os

import duckdb
import pandas as pd

from firecal.dataset import read_dataset, SERIES_DAYS_FILE


def _source_filters(settings):
    """Source filters from Settings: nominal/high confidence, type 0 by default."""
    conf = ", ".join("'" + str(c).replace("'", "''") + "'" for c in settings.CONFIDENCE_KEEP)
    types = ", ".join(str(int(t)) for t in settings.KEEP_TYPES)
    conf_sql = f"d.confidence_class IN ({conf})"
    type_sql = f"(d.type IS NULL OR d.type IN ({types}))" if types else "TRUE"
    return conf_sql, type_sql


def _series_days_relation(con, settings, region):
    """TEMP VIEW series_days(region, date_local, platform) for this connection.

    Prefers the series_days.parquet written by the harmonize rebuild; falls back
    to building it from celldays when the file is missing (slow but correct).
    """
    path = os.path.join(settings.DATA_PROCESSED, SERIES_DAYS_FILE)
    if os.path.exists(path):
        con.execute(f"CREATE OR REPLACE TEMP VIEW series_days AS "
                    f"SELECT * FROM read_parquet('{path.replace(os.sep, '/')}')")
        return
    celldays = read_dataset(settings, "celldays", [region] if region else None)
    from firecal.harmonize.db import _series_days_sql
    con.execute(f"CREATE OR REPLACE TEMP TABLE series_days AS "
                f"{_series_days_sql(celldays, settings.SWITCH_DATE)}")


def hotspot_rows(area, start, end, settings, all_sensors=False, region=None, cover="all"):
    """Yield DataFrames of detection rows in the area/date range, in batches."""
    import duckdb
    from firecal.analytics.cover import cover_exists_latlon

    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads=4")
        con.execute("PRAGMA memory_limit='4GB'")
        root = read_dataset(settings, "detections", [region] if region else None)

        cl = _area_where(area)
        cover_pred = cover_exists_latlon(settings, cover, "d")
        conf_sql, type_sql = _source_filters(settings)
        if all_sensors:
            series_join = ""
            series_filter = "TRUE"
        else:
            _series_days_relation(con, settings, region)
            series_join = ("JOIN series_days AS sd "
                           "ON sd.region = d.region AND sd.date_local = d.date_local")
            series_filter = "d.platform = sd.platform"

        select = f"""
            SELECT d.date_local, d.acq_datetime_utc, d.latitude, d.longitude,
                   d.confidence_class, d.frp, d.daynight, d.sensor, d.platform, d.processing
            FROM {root} AS d
            {series_join}
            WHERE {cl}
              AND d.date_local >= DATE '{start}' AND d.date_local <= DATE '{end}'
              AND {conf_sql}
              AND {type_sql}
              AND {series_filter}
              AND ({cover_pred})
            ORDER BY d.acq_datetime_utc
        """
        con.execute(select)
        while True:
            df = con.fetch_df_chunk(8192)
            if df is None or len(df) == 0:
                break
            yield df
    finally:
        con.close()


def _area_where(area):
    if area.radius_km is not None:
        from firecal.analytics.area import haversine_sql
        return (f"{haversine_sql('latitude', 'longitude', area.lat, area.lon)}"
                f" <= {area.radius_km} + 1e-6")
    return f"latitude BETWEEN {area.s} AND {area.n} AND longitude BETWEEN {area.w} AND {area.e}"


def stream_hotspots_csv(area, start, end, settings, all_sensors=False, region=None, cover="all"):
    """Yield CSV lines (str) for the hotspot rows, streamed from one query."""
    yield "date_local,acq_datetime_utc,latitude,longitude,confidence_class,frp,daynight,sensor,platform,processing\n"
    for df in hotspot_rows(area, start, end, settings, all_sensors=all_sensors,
                           region=region, cover=cover):
        for r in df.itertuples(index=False):
            yield (f"{pd.to_datetime(r.date_local).strftime('%Y-%m-%d')},"
                   f"{pd.to_datetime(r.acq_datetime_utc).isoformat()},"
                   f"{r.latitude},{r.longitude},{r.confidence_class},{r.frp},{r.daynight},"
                   f"{r.sensor},{r.platform},{r.processing}\n")


def hotspots_csv(area, start, end, settings, all_sensors=False, region=None, cover="all"):
    """Whole CSV as one string (small outputs; prefer stream_hotspots_csv)."""
    buf = io.StringIO()
    for line in stream_hotspots_csv(area, start, end, settings, all_sensors=all_sensors,
                                   region=region, cover=cover):
        buf.write(line)
    return buf.getvalue()
