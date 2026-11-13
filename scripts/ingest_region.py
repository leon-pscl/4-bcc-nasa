"""Vectorized (DuckDB) ingest of large FIRMS country files, clipped to a region box.

DuckDB streams the CSV and writes Parquet directly, so Python never holds a chunk of
rows. Timestamps, the local solar date and the uid are computed by the engine
(vectorized), not row by row.
"""

import argparse, glob, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb

VIIRS_SATELLITES = {"N", "N20", "N21", "1", "2", "SNPP", "NOAA20", "NOAA21"}

SQL = """
WITH raw AS (
    SELECT * FROM read_csv(
        '{path}', header = true, auto_detect = true, sample_size = 20000, nullstr = ''
    )
),
typed AS (
    SELECT
        CAST(latitude AS DOUBLE)  AS latitude,
        CAST(longitude AS DOUBLE) AS longitude,
        CAST(acq_date AS DATE)    AS acq_date,
        CAST(acq_time AS INTEGER) AS acq_time,
        satellite, instrument, CAST(confidence AS VARCHAR) AS confidence,
        CAST(version AS VARCHAR) AS version, daynight,
        CAST('{sensor}' AS VARCHAR) AS sensor,
        CAST(frp AS DOUBLE) AS frp,
        CAST(scan AS DOUBLE) AS scan,
        CAST(track AS DOUBLE) AS track,
        CAST({brightness_expr} AS DOUBLE) AS brightness_v,
        CAST({bright_t31_expr} AS DOUBLE) AS bright_t31_v,
        {type_expr} AS type_code
    FROM raw
),
timed AS (
    SELECT *,
        (acq_date + (CAST(acq_time / 100 AS INTEGER) * INTERVAL '1 hour')
                   + (CAST(acq_time % 100 AS INTEGER) * INTERVAL '1 minute')) AS acq_datetime_utc
    FROM typed
),
mapped AS (
    SELECT *,
        CASE WHEN sensor = 'MODIS' THEN
                CASE WHEN CAST(confidence AS INTEGER) <= 29 THEN 1
                     WHEN CAST(confidence AS INTEGER) <= 79 THEN 2
                     ELSE 3 END
             ELSE CASE LOWER(TRIM(confidence))
                      WHEN 'l' THEN 1
                      WHEN 'h' THEN 3
                      ELSE 2 END
        END AS conf_code,
        CASE
            WHEN satellite IN ('Terra','T') THEN 'Terra'
            WHEN satellite IN ('Aqua','A') THEN 'Aqua'
            WHEN satellite IN ('N','SNPP') THEN 'SNPP'
            WHEN satellite IN ('N20','1','NOAA20') THEN 'NOAA20'
            WHEN satellite IN ('N21','2','NOAA21') THEN 'NOAA21'
            ELSE NULL
        END AS platform
    FROM timed
)
SELECT
    md5(platform || '|' || CAST(latitude AS VARCHAR) || '|' ||
        CAST(longitude AS VARCHAR) || '|' || CAST(acq_datetime_utc AS VARCHAR)) AS uid,
    CAST(sensor AS VARCHAR) AS sensor,
    CAST(platform AS VARCHAR) AS platform,
    CASE WHEN RIGHT(TRIM(version), 3) = 'NRT' THEN 'NRT' ELSE 'SP' END AS processing,
    latitude, longitude,
    acq_datetime_utc,
    CAST(acq_datetime_utc + (longitude / 15.0) * INTERVAL '1 hour' AS DATE) AS date_local,
    CAST(UPPER(TRIM(daynight)) AS VARCHAR) AS daynight,
    CAST(TRIM(confidence) AS VARCHAR) AS confidence_raw,
    CASE conf_code WHEN 1 THEN 'low' WHEN 3 THEN 'high' ELSE 'nominal' END AS confidence_class,
    frp, scan, track, brightness_v AS brightness, bright_t31_v AS bright_t31,
    CAST(type_code AS SMALLINT) AS type,
    CAST(TRIM(version) AS VARCHAR) AS version,
    CAST('{source}' AS VARCHAR) AS source_file
FROM mapped
WHERE latitude >= {s} AND latitude <= {n} AND longitude >= {w} AND longitude <= {e}
"""


def detect_sensor(con, path):
    q = ("SELECT DISTINCT satellite FROM read_csv('" + path + "', header=true, auto_detect=true, "
         "sample_size=20000, nullstr='') LIMIT 50")
    sats = {r[0] for r in con.execute(q).fetchall()}
    return "VIIRS" if (sats & VIIRS_SATELLITES) else "MODIS"


def has_column(con, path, name):
    cols = {r[0] for r in con.execute(
        "DESCRIBE SELECT * FROM read_csv('" + path + "', header=true, auto_detect=true, "
        "sample_size=20000, nullstr='')").fetchall()}
    return name in cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region-name", required=True)
    ap.add_argument("--bbox", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--table", default=None, help="duckdb table to append into (default: file)")
    args = ap.parse_args()
    w, s, e, n = [float(x) for x in args.bbox.split(",")]
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    table = args.table or ("det_" + args.region_name)

    t0 = time.time()
    for pattern in args.files:
        for path in sorted(glob.glob(pattern)):
            print("processing", path, flush=True)
            sensor = detect_sensor(con, path)
            type_expr = ("CAST(type AS SMALLINT)" if has_column(con, path, "type")
                         else "CAST(NULL AS SMALLINT)")
            # NRT area CSVs use bright_ti4/bright_ti5 for VIIRS; archive country
            # files use brightness/bright_t31 for both sensors.
            if has_column(con, path, "brightness"):
                brightness_expr, bright_t31_expr = "brightness", "bright_t31"
            else:
                brightness_expr, bright_t31_expr = "bright_ti4", "bright_ti5"
            sql = (SQL.replace("{path}", path.replace("'", "''"))
                      .replace("{source}", path.replace("'", "''"))
                      .replace("{type_expr}", type_expr)
                      .replace("{brightness_expr}", brightness_expr)
                      .replace("{bright_t31_expr}", bright_t31_expr)
                      .replace("{sensor}", sensor)
                      .replace("{w}", str(w)).replace("{s}", str(s))
                      .replace("{e}", str(e)).replace("{n}", str(n)))
            tmp = "data/processed/_part_tmp.parquet"
            con.execute(f"COPY ({sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            exists = con.execute(
                "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = '" + table + "'").fetchone()[0]
            if exists:
                con.execute(f"INSERT INTO {table} SELECT * FROM read_parquet('{tmp}')")
            else:
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet('{tmp}')")
            os.remove(tmp)
            n_rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print("  done, rows so far:", n_rows, flush=True)
    # final export
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    con.execute(f"COPY {table} TO '{args.out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print("wrote", args.out)
    print("total time", time.time() - t0)


if __name__ == "__main__":
    main()
