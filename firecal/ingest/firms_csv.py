"""Parse a FIRMS CSV into the C1 detections shape, with DuckDB.

The file is read by the engine (no Python row loop); the transform is the same
SQL the pipeline uses over big files.
"""

import duckdb
import pandas as pd

from firecal.contracts import validate_detections


def read_firms_csv(path):
    con = duckdb.connect()
    try:
        cols = {r[0] for r in con.execute(
            "DESCRIBE SELECT * FROM read_csv('" + str(path) + "', header=true, "
            "auto_detect=true, sample_size=20000, nullstr='')").fetchall()}
        if "bright_ti4" in cols:
            sensor = "VIIRS"
            brightness_expr, bright_t31_expr = "bright_ti4", "bright_ti5"
        else:
            sensor = "MODIS"
            brightness_expr, bright_t31_expr = "brightness", "bright_t31"
        type_expr = "CAST(type AS SMALLINT)" if "type" in cols else "CAST(NULL AS SMALLINT)"
        sql = f"""
        WITH raw AS (
            SELECT * FROM read_csv('{str(path)}', header=true, auto_detect=true,
                                   sample_size=20000, nullstr='')
        ),
        typed AS (
            SELECT CAST(latitude AS DOUBLE) AS latitude,
                   CAST(longitude AS DOUBLE) AS longitude,
                   CAST(acq_date AS DATE) AS acq_date,
                   CAST(acq_time AS INTEGER) AS acq_time,
                   satellite, CAST(confidence AS VARCHAR) AS confidence,
                   CAST(version AS VARCHAR) AS version, daynight,
                   CAST(frp AS DOUBLE) AS frp, CAST(scan AS DOUBLE) AS scan,
                   CAST(track AS DOUBLE) AS track,
                   CAST({brightness_expr} AS DOUBLE) AS brightness_v,
                   CAST({bright_t31_expr} AS DOUBLE) AS bright_t31_v,
                   {type_expr} AS type_code,
                   CAST('{sensor}' AS VARCHAR) AS sensor
            FROM raw
        ),
        timed AS (
            SELECT *, (acq_date + (CAST(acq_time/100 AS INTEGER) * INTERVAL '1 hour')
                        + (CAST(acq_time%100 AS INTEGER) * INTERVAL '1 minute')) AS acq_datetime_utc
            FROM typed
        ),
        mapped AS (
            SELECT *,
              CASE WHEN sensor='MODIS' THEN
                     CASE WHEN CAST(confidence AS INTEGER) <= 29 THEN 1
                          WHEN CAST(confidence AS INTEGER) <= 79 THEN 2 ELSE 3 END
                   ELSE CASE LOWER(TRIM(confidence)) WHEN 'l' THEN 1 WHEN 'h' THEN 3 ELSE 2 END END AS conf_code,
              CASE WHEN satellite IN ('Terra','T') THEN 'Terra'
                   WHEN satellite IN ('Aqua','A') THEN 'Aqua'
                   WHEN satellite IN ('N','SNPP') THEN 'SNPP'
                   WHEN satellite IN ('N20','1','NOAA20') THEN 'NOAA20'
                   WHEN satellite IN ('N21','2','NOAA21') THEN 'NOAA21'
                   ELSE NULL END AS platform
            FROM timed
        )
        SELECT
            md5(platform || '|' || CAST(latitude AS VARCHAR) || '|' ||
                CAST(longitude AS VARCHAR) || '|' || CAST(acq_datetime_utc AS VARCHAR)) AS uid,
            CAST(sensor AS VARCHAR) AS sensor,
            CAST(platform AS VARCHAR) AS platform,
            CASE WHEN RIGHT(TRIM(version),3)='NRT' THEN 'NRT' ELSE 'SP' END AS processing,
            latitude, longitude, acq_datetime_utc,
            CAST(acq_datetime_utc + (longitude/15.0) * INTERVAL '1 hour' AS DATE) AS date_local,
            CAST(UPPER(TRIM(daynight)) AS VARCHAR) AS daynight,
            CAST(TRIM(confidence) AS VARCHAR) AS confidence_raw,
            CASE conf_code WHEN 1 THEN 'low' WHEN 3 THEN 'high' ELSE 'nominal' END AS confidence_class,
            frp, scan, track, brightness_v AS brightness, bright_t31_v AS bright_t31,
            CAST(type_code AS SMALLINT) AS type,
            CAST(TRIM(version) AS VARCHAR) AS version,
            CAST('{str(path)}' AS VARCHAR) AS source_file
        FROM mapped
        """
        # unknown satellites must fail loudly, never be guessed
        known = ({"Terra", "T", "Aqua", "A"} if sensor == "MODIS"
                 else {"N", "SNPP", "N20", "1", "NOAA20", "N21", "2", "NOAA21"})
        sats = con.execute(
            "SELECT DISTINCT satellite FROM read_csv('" + str(path) + "', header=true, "
            "auto_detect=true, sample_size=20000, nullstr='')").fetchall()
        unknown = sorted({r[0] for r in sats} - known)
        if unknown:
            raise ValueError(f"unknown satellite values: {unknown}")
        out = con.execute(sql).df()
    finally:
        con.close()
    for col in ("sensor", "platform", "processing", "daynight", "confidence_raw",
                "confidence_class", "version", "source_file", "uid"):
        out[col] = out[col].astype("string")
    out["type"] = out["type"].astype("Int8")
    out["acq_datetime_utc"] = pd.to_datetime(out["acq_datetime_utc"])
    out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
    for col in ("latitude", "longitude", "frp", "scan", "track", "brightness", "bright_t31"):
        out[col] = out[col].astype("float64")
    validate_detections(out)
    return out
