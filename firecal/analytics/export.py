"""Export analytics (Stage 4): paged hotspot rows, streamed from one query.

By default only the detections that feed the harmonized series for each date are
exported: Aqua before the switch date; after it, whichever platform the series
used that day (SNPP, else NOAA-20, else NOAA-21, else Aqua). Pass
all_sensors=True to export every detection.
"""

import io

import duckdb
import pandas as pd

from firecal.dataset import read_dataset


def _series_predicate(switch_date):
    """SQL fragment (parenthesized) selecting the detections that feed the series."""
    return f"""
    (
        (d.date_local < DATE '{switch_date}' AND d.platform = 'Aqua')
        OR (d.date_local >= DATE '{switch_date}' AND (
            (EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'SNPP'
                      AND date_local = d.date_local AND region = d.region)
              AND d.platform = 'SNPP')
            OR (NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'SNPP'
                             AND date_local = d.date_local AND region = d.region)
                AND EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'NOAA20'
                             AND date_local = d.date_local AND region = d.region)
                AND d.platform = 'NOAA20')
            OR (NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'SNPP'
                             AND date_local = d.date_local AND region = d.region)
                AND NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'NOAA20'
                                 AND date_local = d.date_local AND region = d.region)
                AND EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'NOAA21'
                             AND date_local = d.date_local AND region = d.region)
                AND d.platform = 'NOAA21')
            OR (NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'SNPP'
                             AND date_local = d.date_local AND region = d.region)
                AND NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'NOAA20'
                                 AND date_local = d.date_local AND region = d.region)
                AND NOT EXISTS (SELECT 1 FROM celldays_dates WHERE platform = 'NOAA21'
                                 AND date_local = d.date_local AND region = d.region)
                AND d.platform = 'Aqua')
        ))
    )
    """


def register_series_views(con, settings, region):
    """Registers the temp table the series predicate reads (materialized once)."""
    celldays = read_dataset(settings, "celldays", [region] if region else None)
    con.execute(f"CREATE OR REPLACE TEMP TABLE celldays_dates AS "
                f"SELECT DISTINCT region, date_local, platform FROM {celldays}")


def hotspot_rows(area, start, end, settings, all_sensors=False, region=None):
    """Yield DataFrames of detection rows in the area/date range, in batches."""
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='1GB'")
    root = read_dataset(settings, "detections", [region] if region else None)

    cl = _area_where(area)
    if all_sensors:
        series = "TRUE"
    else:
        register_series_views(con, settings, region)
        series = _series_predicate(settings.SWITCH_DATE)

    select = f"""
        SELECT d.date_local, d.acq_datetime_utc, d.latitude, d.longitude,
               d.confidence_class, d.frp, d.daynight, d.sensor, d.platform, d.processing
        FROM {root} AS d
        WHERE {cl}
          AND d.date_local >= DATE '{start}' AND d.date_local <= DATE '{end}'
          AND d.confidence_class IN ('nominal', 'high')
          AND (d.type IS NULL OR d.type = 0)
          AND {series}
        ORDER BY d.acq_datetime_utc
    """
    con.execute(select)
    try:
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


def stream_hotspots_csv(area, start, end, settings, all_sensors=False, region=None):
    """Yield CSV lines (str) for the hotspot rows, streamed from one query."""
    yield "date_local,acq_datetime_utc,latitude,longitude,confidence_class,frp,daynight,sensor,platform,processing\n"
    for df in hotspot_rows(area, start, end, settings, all_sensors=all_sensors, region=region):
        for r in df.itertuples(index=False):
            yield (f"{pd.to_datetime(r.date_local).strftime('%Y-%m-%d')},"
                   f"{pd.to_datetime(r.acq_datetime_utc).isoformat()},"
                   f"{r.latitude},{r.longitude},{r.confidence_class},{r.frp},{r.daynight},"
                   f"{r.sensor},{r.platform},{r.processing}\n")


def hotspots_csv(area, start, end, settings, all_sensors=False, region=None):
    """Whole CSV as one string (small outputs; prefer stream_hotspots_csv)."""
    buf = io.StringIO()
    for line in stream_hotspots_csv(area, start, end, settings, all_sensors=all_sensors, region=region):
        buf.write(line)
    return buf.getvalue()
