"""Parse a FIRMS CSV into the C1 detections shape."""

import hashlib
from datetime import date, datetime, timedelta

import pandas as pd

from firecal.contracts import validate_detections


MODIS_SAT_MAP = {"Terra": "Terra", "T": "Terra", "Aqua": "Aqua", "A": "Aqua"}
VIIRS_SAT_MAP = {"N": "SNPP", "N20": "NOAA20", "1": "NOAA20", "NOAA20": "NOAA20",
                 "N21": "NOAA21", "2": "NOAA21", "NOAA21": "NOAA21"}


def _confidence_class(sensor, raw):
    raw = str(raw).strip()
    if sensor == "MODIS":
        try:
            v = int(float(raw))
        except ValueError:
            return "nominal"
        if v <= 29:
            return "low"
        if v <= 79:
            return "nominal"
        return "high"
    # VIIRS
    low = raw.lower()
    if low == "l":
        return "low"
    if low == "h":
        return "high"
    return "nominal"


def read_firms_csv(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if len(df) == 0:
        # header-only: return empty C1 frame with correct dtypes
        sensor = "VIIRS" if "bright_ti4" in df.columns else "MODIS"
        empty = pd.DataFrame(columns=[
            "uid", "sensor", "platform", "processing", "latitude", "longitude",
            "acq_datetime_utc", "date_local", "daynight", "confidence_raw",
            "confidence_class", "frp", "scan", "track", "brightness", "bright_t31",
            "type", "version", "source_file",
        ])
        empty["sensor"] = empty["sensor"].astype("string")
        empty["platform"] = empty["platform"].astype("string")
        empty["processing"] = empty["processing"].astype("string")
        empty["latitude"] = empty["latitude"].astype("float64")
        empty["longitude"] = empty["longitude"].astype("float64")
        empty["acq_datetime_utc"] = pd.to_datetime(empty["acq_datetime_utc"])
        empty["daynight"] = empty["daynight"].astype("string")
        empty["confidence_raw"] = empty["confidence_raw"].astype("string")
        empty["confidence_class"] = empty["confidence_class"].astype("string")
        empty["frp"] = empty["frp"].astype("float64")
        empty["scan"] = empty["scan"].astype("float64")
        empty["track"] = empty["track"].astype("float64")
        empty["brightness"] = empty["brightness"].astype("float64")
        empty["bright_t31"] = empty["bright_t31"].astype("float64")
        empty["type"] = empty["type"].astype("Int8")
        empty["version"] = empty["version"].astype("string")
        empty["source_file"] = empty["source_file"].astype("string")
        empty["uid"] = empty["uid"].astype("string")
        return empty
    if "bright_ti4" in df.columns:
        sensor = "VIIRS"
        df = df.rename(columns={"bright_ti4": "brightness", "bright_ti5": "bright_t31"})
    elif "brightness" in df.columns:
        sensor = "MODIS"
    else:
        raise ValueError("cannot detect sensor from columns")

    if sensor == "MODIS":
        sat_map = MODIS_SAT_MAP
    else:
        sat_map = VIIRS_SAT_MAP

    # validate satellites
    unknown = set(df["satellite"].astype(str).str.strip()) - set(sat_map.keys())
    if unknown:
        raise ValueError(f"unknown satellite values: {sorted(unknown)}")

    platforms = df["satellite"].astype(str).str.strip().map(sat_map)

    # processing
    processing = df["version"].astype(str).str.strip().apply(
        lambda v: "NRT" if str(v).endswith("NRT") else "SP"
    )

    # UTC datetime
    def parse_dt(row):
        d = str(row["acq_date"]).strip()
        t = str(row["acq_time"]).strip()
        if t == "":
            t = "0"
        t = t.zfill(4)
        hh = int(t[:2])
        mm = int(t[2:4])
        dt = datetime.strptime(d, "%Y-%m-%d")
        return dt.replace(hour=hh, minute=mm)

    acq_utc = df.apply(parse_dt, axis=1)

    # local solar date
    def local_date(row, utc):
        lon = float(row["longitude"])
        local = utc + timedelta(hours=lon / 15.0)
        return local.date()

    date_local = [local_date(df.iloc[i], acq_utc.iloc[i]) for i in range(len(df))]

    confidence_raw = df["confidence"].astype(str).str.strip()
    confidence_class = [ _confidence_class(sensor, v) for v in confidence_raw ]

    # type column
    if "type" in df.columns:
        type_series = pd.to_numeric(df["type"], errors="coerce").astype("Int8")
    else:
        type_series = pd.Series([pd.NA] * len(df), dtype="Int8")

    out = pd.DataFrame({
        "uid": None,
        "sensor": sensor,
        "platform": platforms.astype(str),
        "processing": processing.astype(str),
        "latitude": pd.to_numeric(df["latitude"], errors="coerce").astype("float64"),
        "longitude": pd.to_numeric(df["longitude"], errors="coerce").astype("float64"),
        "acq_datetime_utc": pd.to_datetime(acq_utc),
        "date_local": date_local,
        "daynight": df["daynight"].astype(str).str.strip().str.upper(),
        "confidence_raw": confidence_raw.astype(str),
        "confidence_class": confidence_class,
        "frp": pd.to_numeric(df["frp"], errors="coerce").astype("float64"),
        "scan": pd.to_numeric(df["scan"], errors="coerce").astype("float64"),
        "track": pd.to_numeric(df["track"], errors="coerce").astype("float64"),
        "brightness": pd.to_numeric(df["brightness"], errors="coerce").astype("float64"),
        "bright_t31": pd.to_numeric(df["bright_t31"], errors="coerce").astype("float64"),
        "type": type_series,
        "version": df["version"].astype(str).str.strip(),
        "source_file": str(path),
    })

    # uid hash
    def make_uid(row):
        base = f"{row['platform']}|{row['latitude']}|{row['longitude']}|{row['acq_datetime_utc']}"
        return hashlib.sha256(base.encode()).hexdigest()

    out["uid"] = out.apply(make_uid, axis=1)

    # dtypes
    out["sensor"] = out["sensor"].astype("string")
    out["platform"] = out["platform"].astype("string")
    out["processing"] = out["processing"].astype("string")
    out["daynight"] = out["daynight"].astype("string")
    out["confidence_raw"] = out["confidence_raw"].astype("string")
    out["confidence_class"] = out["confidence_class"].astype("string")
    out["version"] = out["version"].astype("string")
    out["source_file"] = out["source_file"].astype("string")
    out["type"] = out["type"].astype("Int8")

    validate_detections(out)
    return out