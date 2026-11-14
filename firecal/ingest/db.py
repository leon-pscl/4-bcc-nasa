"""DuckDB ingest of FIRMS CSV files into the detections dataset (C1).

All the row-level work happens in SQL: DuckDB streams the CSV and writes Parquet
partitions, so Python never holds the file. Timestamps, the local solar date and
the uid are computed by the engine.
"""

import glob
import os
import shutil

import duckdb

from firecal.dataset import fingerprint, write_partition, dataset_dir

MODIS_SATELLITES = {"Terra", "T", "Aqua", "A"}
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
        CAST(frp AS DOUBLE) AS frp,
        CAST(scan AS DOUBLE) AS scan,
        CAST(track AS DOUBLE) AS track,
        CAST({brightness_expr} AS DOUBLE) AS brightness_v,
        CAST({bright_t31_expr} AS DOUBLE) AS bright_t31_v,
        {type_expr} AS type_code,
        CAST('{sensor}' AS VARCHAR) AS sensor
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
    CAST('{source}' AS VARCHAR) AS source_file,
    CAST('{region}' AS VARCHAR) AS region,
    CAST(EXTRACT(year FROM acq_date) AS INTEGER) AS year
FROM mapped
WHERE latitude >= {s} AND latitude <= {n} AND longitude >= {w} AND longitude <= {e}
-- the manual SP archive files carry a few byte-identical rows twice; uid is
-- unique per observation, so dedup on the full output keeps SP-vs-NRT rows
-- (which differ in `processing`) while collapsing literal copies
-- the manual SP archive files carry a few byte-identical rows twice; uid is
-- unique per observation, so dedup on uid (SP preferred) collapses literal
-- copies and keeps the SP version when both exist in one file
QUALIFY ROW_NUMBER() OVER (PARTITION BY uid ORDER BY CASE WHEN processing = 'SP' THEN 0 ELSE 1 END) = 1
"""


def connect(threads=4, memory_limit="4GB"):
    con = duckdb.connect()
    con.execute(f"PRAGMA threads={threads}")
    con.execute(f"PRAGMA memory_limit='{memory_limit}'")
    return con


def _columns(con, path):
    return {r[0] for r in con.execute(
        "DESCRIBE SELECT * FROM read_csv('" + path + "', header=true, auto_detect=true, "
        "sample_size=20000, nullstr='')").fetchall()}


def detect_sensor(con, path):
    q = ("SELECT DISTINCT satellite FROM read_csv('" + path + "', header=true, auto_detect=true, "
         "sample_size=20000, nullstr='') LIMIT 50")
    sats = {r[0] for r in con.execute(q).fetchall()}
    return "VIIRS" if (sats & VIIRS_SATELLITES) else "MODIS"


def build_sql(con, path, sensor, region, bbox):
    w, s, e, n = bbox
    cols = _columns(con, path)
    type_expr = "CAST(type AS SMALLINT)" if "type" in cols else "CAST(NULL AS SMALLINT)"
    if "brightness" in cols:
        brightness_expr, bright_t31_expr = "brightness", "bright_t31"
    else:
        brightness_expr, bright_t31_expr = "bright_ti4", "bright_ti5"
    return (SQL.replace("{path}", path.replace("\\", "/").replace("'", "''"))
               .replace("{source}", path.replace("\\", "/").replace("'", "''"))
               .replace("{region}", region)
               .replace("{type_expr}", type_expr)
               .replace("{brightness_expr}", brightness_expr)
               .replace("{bright_t31_expr}", bright_t31_expr)
               .replace("{sensor}", sensor)
               .replace("{w}", str(w)).replace("{s}", str(s))
               .replace("{e}", str(e)).replace("{n}", str(n)))


def expand(patterns):
    paths = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(pat)))
    return paths


def read_firms_csv(path):
    """Read one FIRMS CSV into the C1 shape (used by tests and small files)."""
    con = connect()
    try:
        cols = {r[0] for r in con.execute(
            "DESCRIBE SELECT * FROM read_csv('" + str(path) + "', header=true, "
            "auto_detect=true, sample_size=20000, nullstr='')").fetchall()}
        sats = {r[0] for r in con.execute(
            "SELECT DISTINCT satellite FROM read_csv('" + str(path) + "', header=true, "
            "auto_detect=true, sample_size=20000, nullstr='')").fetchall()}
        if "bright_ti4" in cols:
            sensor = "VIIRS"
            known = {"N", "SNPP", "N20", "1", "NOAA20", "N21", "2", "NOAA21"}
        else:
            sensor = "MODIS"
            known = {"Terra", "T", "Aqua", "A"}
        unknown = sorted({str(x).strip() for x in sats} - known)
        if unknown:
            raise ValueError(f"unknown satellite values: {unknown}")
        sql = build_sql(con, str(path), sensor, "test", (-180, -90, 180, 90))
        out = con.execute(sql).df()
    finally:
        con.close()
    if len(out):
        import pandas as pd
        out = out.drop(columns=["region", "year"])
        for col in ("sensor", "platform", "processing", "daynight",
                    "confidence_raw", "confidence_class", "version",
                    "source_file", "uid"):
            out[col] = out[col].astype("string")
        out["type"] = out["type"].astype("Int8")
        out["acq_datetime_utc"] = pd.to_datetime(out["acq_datetime_utc"])
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        for col in ("latitude", "longitude", "frp", "scan", "track",
                    "brightness", "bright_t31"):
            out[col] = out[col].astype("float64")
    else:
        import pandas as pd
        out = pd.DataFrame(columns=["uid", "sensor", "platform", "processing",
                                    "latitude", "longitude", "acq_datetime_utc",
                                    "date_local", "daynight", "confidence_raw",
                                    "confidence_class", "frp", "scan", "track",
                                    "brightness", "bright_t31", "type", "version",
                                    "source_file"])
        out["uid"] = out["uid"].astype("string")
        out["sensor"] = out["sensor"].astype("string")
        out["platform"] = out["platform"].astype("string")
        out["processing"] = out["processing"].astype("string")
        out["latitude"] = out["latitude"].astype("float64")
        out["longitude"] = out["longitude"].astype("float64")
        out["acq_datetime_utc"] = pd.to_datetime(out["acq_datetime_utc"])
        out["daynight"] = out["daynight"].astype("string")
        out["confidence_raw"] = out["confidence_raw"].astype("string")
        out["confidence_class"] = out["confidence_class"].astype("string")
        out["frp"] = out["frp"].astype("float64")
        out["scan"] = out["scan"].astype("float64")
        out["track"] = out["track"].astype("float64")
        out["brightness"] = out["brightness"].astype("float64")
        out["bright_t31"] = out["bright_t31"].astype("float64")
        out["type"] = out["type"].astype("Int8")
        out["version"] = out["version"].astype("string")
        out["source_file"] = out["source_file"].astype("string")
    from firecal.contracts import validate_detections
    validate_detections(out)
    return out


def file_fingerprint(path):
    st = os.stat(path)
    return fingerprint(os.path.abspath(path), st.st_size, int(st.st_mtime))


def ingest_files(con, paths, region, bbox, settings, dataset="detections",
                 state=None, dry_run=False):
    """Ingest CSV files into the detections dataset, per (region, year) partition.

    Each file is scanned once into a staging area partitioned by year; the
    published partition for a year is the union of the staging parts of every
    file that contributes to it. Only partitions whose inputs changed are
    rebuilt.
    """
    from firecal.dataset import DETECTIONS, load_state, partition_key, save_state

    state = state if state is not None else load_state(settings)
    ds_state = state.setdefault(dataset, {})
    files_state = state.setdefault("files", {})
    staging_root = os.path.join(settings.DATA_PROCESSED, "_staging", region)
    written = []
    rows_written = 0
    changed = []  # (path, fp, stage_dir, years)

    for path in paths:
        fp = file_fingerprint(path)
        prev = files_state.get(os.path.abspath(path))
        if prev and prev.get("fingerprint") == fp and not dry_run:
            continue  # unchanged file: its partitions are already published
        sensor = detect_sensor(con, path)
        sql = build_sql(con, path, sensor, region, bbox)
        file_key = fingerprint(fp)[:16]
        import tempfile as _tf
        os.makedirs(staging_root, exist_ok=True)
        stage_dir = _tf.mkdtemp(prefix="_part_", dir=staging_root)
        os.makedirs(stage_dir, exist_ok=True)
        # one scan, partitioned by year
        con.execute(
            f"COPY ({sql}) TO '{stage_dir.replace(os.sep, '/')}' "
            f"(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (region, year), OVERWRITE_OR_IGNORE)"
        )
        stage_glob = f"{stage_dir.replace(os.sep, '/')}/*/*/*.parquet"
        if not glob.glob(stage_glob):
            # empty result (header-only response): nothing to write
            if not dry_run:
                files_state[os.path.abspath(path)] = {
                    "fingerprint": fp, "years": [], "staging": None,
                }
            continue
        years = sorted(int(r[0]) for r in con.execute(
            f"SELECT DISTINCT year FROM read_parquet('{stage_glob}')"
        ).fetchall())
        rows_written += con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{stage_glob}')"
        ).fetchone()[0]
        changed.append((path, fp, stage_dir, years))
        if not dry_run:
            files_state[os.path.abspath(path)] = {
                "fingerprint": fp, "years": years, "staging": stage_dir,
            }

    if not changed:
        if not dry_run:
            save_state(settings, state)
        return written, rows_written

    affected_years = set()
    for _, _, _, yrs in changed:
        affected_years.update(yrs)

    for year in sorted(affected_years):
        key = partition_key(region, year)
        part_fp = fingerprint(*[c[1] for c in changed], year)
        if ds_state.get(key, {}).get("fingerprint") == part_fp and not dry_run:
            continue
        parts = []
        new_parts_set = set()
        for _, _, sd, yrs in changed:
            if year in yrs:
                for f in _year_parts([(sd, yrs)], region, year):
                    p = f.replace(os.sep, "/")
                    parts.append(p)
                    new_parts_set.add(p)
        # preserve unchanged rows from the existing published partition
        existing = dataset_dir(settings, dataset) / f"region={region}" / f"year={year}"
        if existing.exists():
            for f in existing.glob("*.parquet"):
                parts.append(str(f).replace(os.sep, "/"))
        if not parts:
            continue
        union = "read_parquet([" + ", ".join(f"'{p}'" for p in parts) + "])"
        # dedup by uid: new rows win; existing rows whose uid already appears in
        # the new files are dropped (SP-over-NRT for the same observation). Using
        # an anti-join avoids sorting the whole published partition, which OOMs
        # on large years.
        new_parts = [p for p in parts if p in new_parts_set]
        old_parts = [p for p in parts if p not in new_parts_set]
        cols = ("uid, sensor, platform, processing, latitude, longitude, acq_datetime_utc, "
                "date_local, daynight, confidence_raw, confidence_class, frp, scan, track, "
                "brightness, bright_t31, type, version, source_file, region, year")
        if new_parts and old_parts:
            new_union = "read_parquet([" + ", ".join(f"'{p}'" for p in new_parts) + "])"
            old_union = "read_parquet([" + ", ".join(f"'{p}'" for p in old_parts) + "])"
            part_sql = f"""
            SELECT {cols} FROM {new_union}
            UNION ALL
            SELECT {cols} FROM {old_union} o
            WHERE o.uid NOT IN (SELECT uid FROM {new_union})
            """
        else:
            part_sql = f"SELECT {cols} FROM {union}"
        if not dry_run:
            write_partition(con, part_sql, settings, dataset, region, year)
        ds_state[key] = {"fingerprint": part_fp}
        written.append(key)
    if not dry_run:
        save_state(settings, state)
    return written, rows_written


def _year_parts(stagings, region, year):
    """Staging parts (one per source file) that contribute to a (region, year)."""
    out = []
    for stage_dir, years in stagings:
        if year not in years:
            continue
        part = os.path.join(stage_dir, f"region={region}", f"year={year}")
        if os.path.isdir(part):
            files = [os.path.join(part, f) for f in os.listdir(part) if f.endswith(".parquet")]
            if files:
                out.append(files[0])
    return out
