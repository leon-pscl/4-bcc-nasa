"""Parse a FIRMS CSV into the C1 detections table."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from firecal.contracts import validate_detections


MODIS_PLATFORM_MAP = {"Terra": "Terra", "T": "Terra", "Aqua": "Aqua", "A": "Aqua"}
VIIRS_PLATFORM_MAP = {"N": "SNPP", "1": "NOAA20", "N20": "NOAA20", "N21": "NOAA21", "2": "NOAA21"}


def _sensor_from_columns(df: pd.DataFrame) -> str:
    if "bright_ti4" in df.columns:
        return "VIIRS"
    if "brightness" in df.columns:
        return "MODIS"
    raise ValueError("cannot detect sensor: missing brightness columns")


def read_firms_csv(path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path)
    sensor = _sensor_from_columns(df)
    if sensor == "VIIRS":
        df = df.rename(columns={"bright_ti4": "brightness", "bright_ti5": "bright_t31"})

    # platform mapping
    if sensor == "MODIS":
        mapping = MODIS_PLATFORM_MAP
    else:
        mapping = VIIRS_PLATFORM_MAP
    if "satellite" not in df.columns:
        raise ValueError("missing 'satellite' column")
    unknown = [v for v in df["satellite"].astype(str).str.strip().unique() if v not in mapping]
    if unknown:
        raise ValueError(f"unknown satellite values: {unknown}")
    df["platform"] = df["satellite"].astype(str).str.strip().map(mapping)
    df["sensor"] = sensor

    # timestamps
    date_part = df["acq_date"].astype(str).str.replace("-", "", regex=False)
    time_part = pd.to_numeric(df["acq_time"], errors="coerce").fillna(0).astype("int64").astype(str).str.zfill(4)
    df["acq_datetime_utc"] = pd.to_datetime(date_part + time_part, format="%Y%m%d%H%M", errors="coerce")
    df["local"] = df["acq_datetime_utc"] + pd.to_timedelta(df["longitude"] / 15.0, unit="h")
    df["date_local"] = df["local"].dt.date

    # confidence
    df["confidence_raw"] = df["confidence"].astype(str)
    if sensor == "MODIS":
        numeric = pd.to_numeric(df["confidence"], errors="coerce")
        cls = pd.Series("nominal", index=df.index, dtype="object")
        cls[numeric < 30] = "low"
        cls[numeric >= 80] = "high"
        cls[numeric.isna()] = "nominal"
    else:
        letters = df["confidence"].astype(str).str.lower().str.strip()
        cls = letters.map({"l": "low", "n": "nominal", "h": "high"}).fillna("nominal")
    df["confidence_class"] = cls

    # processing
    if "version" in df.columns:
        df["processing"] = df["version"].astype(str).apply(lambda v: "NRT" if v.endswith("NRT") else "SP")
    else:
        df["processing"] = "SP"

    # type column
    if "type" in df.columns:
        df["type"] = pd.to_numeric(df["type"], errors="coerce").astype("Int8")
    else:
        df["type"] = pd.array([pd.NA] * len(df), dtype="Int8")

    # uid
    df["uid"] = [
        hashlib.sha1(f"{p}|{la}|{lo}|{dt}".encode()).hexdigest()
        for p, la, lo, dt in zip(df["platform"], df["latitude"], df["longitude"], df["acq_datetime_utc"])
    ]

    # numeric casts
    for c in ("latitude", "longitude", "frp", "scan", "track", "brightness", "bright_t31"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        else:
            df[c] = np.nan

    df["version"] = df.get("version", pd.Series([""] * len(df))).astype(str)
    df["source_file"] = path.name
    df["daynight"] = df["daynight"].astype(str)

    out = pd.DataFrame({
        "uid": df["uid"].astype(str),
        "sensor": df["sensor"].astype(str),
        "platform": df["platform"].astype(str),
        "processing": df["processing"].astype(str),
        "latitude": df["latitude"],
        "longitude": df["longitude"],
        "acq_datetime_utc": df["acq_datetime_utc"],
        "date_local": df["date_local"],
        "daynight": df["daynight"].astype(str),
        "confidence_raw": df["confidence_raw"].astype(str),
        "confidence_class": df["confidence_class"].astype(str),
        "frp": df["frp"],
        "scan": df["scan"],
        "track": df["track"],
        "brightness": df["brightness"],
        "bright_t31": df["bright_t31"],
        "type": df["type"],
        "version": df["version"].astype(str),
        "source_file": df["source_file"].astype(str),
    })
    validate_detections(out)
    return out