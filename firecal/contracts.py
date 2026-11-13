"""Data contracts (column lists and validators) for firecal tables."""

import datetime
from typing import List

import pandas as pd


# C1: detections
DETECTIONS_COLUMNS: List[str] = [
    "uid", "sensor", "platform", "processing", "latitude", "longitude",
    "acq_datetime_utc", "date_local", "daynight", "confidence_raw",
    "confidence_class", "frp", "scan", "track", "brightness", "bright_t31",
    "type", "version", "source_file",
]

# C2: cell-days
CELLDAYS_COLUMNS: List[str] = [
    "cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform",
    "n_detections", "frp_sum",
]

# C3: calibration
CALIBRATION_COLUMNS: List[str] = [
    "region", "platform", "reference", "tile_id", "month", "k",
    "modis_celldays", "viirs_celldays", "level",
]

# C4: harmonized (no sensor/platform)
HARMONIZED_COLUMNS: List[str] = [
    "region", "cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis",
]


def _check_columns(df: pd.DataFrame, required: List[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns: {missing}")


def _is_string(series: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(series)


def _check_date_local(df: pd.DataFrame, name: str) -> None:
    if "date_local" not in df.columns:
        return
    bad = [v for v in df["date_local"].tolist() if not isinstance(v, (datetime.date, pd.Timestamp))]
    if bad:
        raise ValueError(f"{name}: column 'date_local' must hold date values, got {bad[:3]}")


def _check_dtypes(df: pd.DataFrame, expected: dict, name: str) -> None:
    for col, exp in expected.items():
        if col not in df.columns:
            continue
        series = df[col]
        if exp == "string":
            if not _is_string(series):
                raise ValueError(f"{name}: column '{col}' expected string, got {series.dtype}")
        elif exp == "datetime64":
            if not pd.api.types.is_datetime64_any_dtype(series):
                raise ValueError(f"{name}: column '{col}' expected datetime, got {series.dtype}")
        elif exp == "Int8":
            if str(series.dtype) != "Int8":
                raise ValueError(f"{name}: column '{col}' expected Int8, got {series.dtype}")
        elif exp == "int32":
            if str(series.dtype) != "int32":
                raise ValueError(f"{name}: column '{col}' expected int32, got {series.dtype}")
        elif exp == "int64":
            if str(series.dtype) != "int64":
                raise ValueError(f"{name}: column '{col}' expected int64, got {series.dtype}")
        elif exp == "int8":
            if str(series.dtype) != "int8":
                raise ValueError(f"{name}: column '{col}' expected int8, got {series.dtype}")
        elif exp == "float64":
            if str(series.dtype) != "float64":
                raise ValueError(f"{name}: column '{col}' expected float64, got {series.dtype}")
        else:
            if str(series.dtype) != exp:
                raise ValueError(f"{name}: column '{col}' expected {exp}, got {series.dtype}")


DETECTIONS_DTYPES = {
    "uid": "string", "sensor": "string", "platform": "string",
    "processing": "string", "latitude": "float64", "longitude": "float64",
    "acq_datetime_utc": "datetime64", "date_local": "date",
    "daynight": "string", "confidence_raw": "string",
    "confidence_class": "string", "frp": "float64", "scan": "float64",
    "track": "float64", "brightness": "float64", "bright_t31": "float64",
    "type": "Int8", "version": "string", "source_file": "string",
}

CELLDAYS_DTYPES = {
    "cell_lat_idx": "int32", "cell_lon_idx": "int32", "tile_id": "string",
    "date_local": "date", "platform": "string", "n_detections": "int32",
    "frp_sum": "float64",
}

CALIBRATION_DTYPES = {
    "region": "string", "platform": "string", "reference": "string",
    "tile_id": "string", "month": "int8", "k": "float64",
    "modis_celldays": "int64", "viirs_celldays": "int64", "level": "string",
}

HARMONIZED_DTYPES = {
    "region": "string", "cell_lat_idx": "int32", "cell_lon_idx": "int32",
    "tile_id": "string", "date_local": "date", "value": "float64",
    "basis": "string",
}


def validate_detections(df: pd.DataFrame) -> None:
    _check_columns(df, DETECTIONS_COLUMNS, "detections")
    _check_dtypes(df, {k: v for k, v in DETECTIONS_DTYPES.items() if v != "date"}, "detections")
    _check_date_local(df, "detections")


def validate_celldays(df: pd.DataFrame) -> None:
    _check_columns(df, CELLDAYS_COLUMNS, "celldays")
    _check_dtypes(df, {k: v for k, v in CELLDAYS_DTYPES.items() if v != "date"}, "celldays")
    _check_date_local(df, "celldays")


def validate_calibration(df: pd.DataFrame) -> None:
    _check_columns(df, CALIBRATION_COLUMNS, "calibration")
    _check_dtypes(df, {k: v for k, v in CALIBRATION_DTYPES.items() if v != "date"}, "calibration")


VALID_BASIS = {"viirs", "viirs_noaa20", "viirs_noaa21", "modis_scaled", "modis_gapfill"}


def validate_harmonized(df: pd.DataFrame) -> None:
    _check_columns(df, HARMONIZED_COLUMNS, "harmonized")
    if "sensor" in df.columns or "platform" in df.columns or "reference" in df.columns:
        raise ValueError("harmonized: must not contain 'sensor', 'platform' or 'reference' column")
    bad = set(df["basis"].dropna().unique()) - VALID_BASIS
    if bad:
        raise ValueError(f"harmonized: unknown basis values: {sorted(bad)}")
    _check_dtypes(df, {k: v for k, v in HARMONIZED_DTYPES.items() if v != "date"}, "harmonized")
    _check_date_local(df, "harmonized")