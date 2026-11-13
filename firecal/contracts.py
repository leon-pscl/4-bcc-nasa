"""Data contracts (column lists and validators) for firecal tables."""

from typing import Dict, List, Tuple

import pandas as pd


# C1: detections
DETECTIONS_COLUMNS: List[str] = [
    "uid", "sensor", "platform", "processing", "latitude", "longitude",
    "acq_datetime_utc", "date_local", "daynight", "confidence_raw",
    "confidence_class", "frp", "scan", "track", "brightness", "bright_t31",
    "type", "version", "source_file",
]

DETECTIONS_DTYPES: Dict[str, str] = {
    "uid": "string",
    "sensor": "string",
    "platform": "string",
    "processing": "string",
    "latitude": "float64",
    "longitude": "float64",
    "acq_datetime_utc": "datetime64[ns]",
    "date_local": "object",  # date
    "daynight": "string",
    "confidence_raw": "string",
    "confidence_class": "string",
    "frp": "float64",
    "scan": "float64",
    "track": "float64",
    "brightness": "float64",
    "bright_t31": "float64",
    "type": "Int8",
    "version": "string",
    "source_file": "string",
}

# C4: harmonized (no sensor/platform)
HARMONIZED_COLUMNS: List[str] = [
    "cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis",
]

HARMONIZED_DTYPES: Dict[str, str] = {
    "cell_lat_idx": "int32",
    "cell_lon_idx": "int32",
    "tile_id": "string",
    "date_local": "object",
    "value": "float64",
    "basis": "string",
}


def _check_columns(df: pd.DataFrame, required: List[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns: {missing}")


def _check_dtypes(df: pd.DataFrame, dtypes: Dict[str, str], name: str) -> None:
    for col, expected in dtypes.items():
        if col not in df.columns:
            continue
        actual = str(df[col].dtype)
        if expected == "object":
            # accept date-like or object
            continue
        if expected == "datetime64[ns]":
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                raise ValueError(f"{name}: column '{col}' expected datetime, got {actual}")
            continue
        if expected == "Int8":
            if str(df[col].dtype) != "Int8":
                raise ValueError(f"{name}: column '{col}' expected Int8, got {actual}")
            continue
        if actual != expected:
            raise ValueError(f"{name}: column '{col}' expected {expected}, got {actual}")


def validate_detections(df: pd.DataFrame) -> None:
    _check_columns(df, DETECTIONS_COLUMNS, "detections")
    _check_dtypes(df, DETECTIONS_DTYPES, "detections")


def validate_harmonized(df: pd.DataFrame) -> None:
    _check_columns(df, HARMONIZED_COLUMNS, "harmonized")
    if "sensor" in df.columns or "platform" in df.columns:
        raise ValueError("harmonized: must not contain 'sensor' or 'platform' column")
    _check_dtypes(df, HARMONIZED_DTYPES, "harmonized")
