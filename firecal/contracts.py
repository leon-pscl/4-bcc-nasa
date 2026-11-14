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

# C9: per-cell cover (MCD12Q1 500 m, yearly)
COVER_COLUMNS: List[str] = [
    "region", "cell_lat_idx", "cell_lon_idx", "year", "cover_class",
    "forest_pct", "crop_pct", "other_veg_pct", "land_pixels",
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

COVER_DTYPES = {
    "region": "string", "cell_lat_idx": "int32", "cell_lon_idx": "int32", "year": "int16",
    "cover_class": "string", "forest_pct": "int8", "crop_pct": "int8",
    "other_veg_pct": "int8", "land_pixels": "int32",
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


VALID_BASIS = {"viirs", "viirs_noaa20", "viirs_noaa21", "modis_scaled", "modis_gapfill", "terra_gapfill"}
VALID_COVER_CLASS = {"forest", "farmland", "other_vegetation", "other"}


def validate_cover(df: pd.DataFrame) -> None:
    _check_columns(df, COVER_COLUMNS, "cell_cover")
    _check_dtypes(df, {k: v for k, v in COVER_DTYPES.items() if v != "date"}, "cell_cover")
    bad = set(df["cover_class"].dropna().unique()) - VALID_COVER_CLASS
    if bad:
        raise ValueError(f"cell_cover: unknown cover_class values: {sorted(bad)}")
    for col in ("forest_pct", "crop_pct", "other_veg_pct"):
        vals = df[col].dropna()
        if len(vals) and (vals < 0).any():
            raise ValueError(f"cell_cover: {col} must be 0..100, got min {vals.min()}")
    if "year" in df.columns:
        ys = df["year"].dropna()
        if len(ys) and ((ys < 2001) | (ys > 2025)).any():
            raise ValueError(f"cell_cover: year out of range 2001..2025")
    if (df["land_pixels"] <= 0).any():
        raise ValueError("cell_cover: land_pixels must be > 0 (water cells carry no row)")


def validate_harmonized(df: pd.DataFrame) -> None:
    _check_columns(df, HARMONIZED_COLUMNS, "harmonized")
    if "sensor" in df.columns or "platform" in df.columns or "reference" in df.columns:
        raise ValueError("harmonized: must not contain 'sensor', 'platform' or 'reference' column")
    bad = set(df["basis"].dropna().unique()) - VALID_BASIS
    if bad:
        raise ValueError(f"harmonized: unknown basis values: {sorted(bad)}")
    _check_dtypes(df, {k: v for k, v in HARMONIZED_DTYPES.items() if v != "date"}, "harmonized")
    _check_date_local(df, "harmonized")