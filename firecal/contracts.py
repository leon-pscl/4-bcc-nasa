"""Data contracts: column lists, dtypes and validate_* helpers (section 6).

Each validator raises a clear ``ValueError`` on any mismatch.
"""

from typing import List

import pandas as pd


DETECTIONS_COLUMNS: List[str] = [
    "uid", "sensor", "platform", "processing", "latitude", "longitude",
    "acq_datetime_utc", "date_local", "daynight", "confidence_raw",
    "confidence_class", "frp", "scan", "track", "brightness", "bright_t31",
    "type", "version", "source_file",
]

CELLDAYS_COLUMNS: List[str] = [
    "cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "platform",
    "n_detections", "frp_sum",
]

CALIBRATION_COLUMNS: List[str] = [
    "tile_id", "month", "k", "modis_celldays", "viirs_celldays", "level",
]

HARMONIZED_COLUMNS: List[str] = [
    "cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis",
]


class ContractError(ValueError):
    pass


def _require_columns(df: pd.DataFrame, expected: List[str], table: str) -> None:
    if list(df.columns) != expected:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        raise ContractError(
            f"{table}: columns mismatch. missing={missing} extra={extra}"
        )


def _is_string_dtype(dtype) -> bool:
    return str(dtype) in ("object", "string") or "str" in str(dtype).lower()


def validate_detections(df: pd.DataFrame) -> None:
    _require_columns(df, DETECTIONS_COLUMNS, "detections")
    if df["uid"].duplicated().any():
        raise ContractError("detections: uid must be unique")
    for c in ("latitude", "longitude", "frp", "scan", "track", "brightness", "bright_t31"):
        if not pd.api.types.is_float_dtype(df[c]):
            raise ContractError(f"detections: {c} must be float64")
    if not pd.api.types.is_datetime64_any_dtype(df["acq_datetime_utc"]):
        raise ContractError("detections: acq_datetime_utc must be a timestamp")
    if str(df["type"].dtype) not in ("Int8", "object"):
        raise ContractError("detections: type must be nullable Int8")
    for c in ("uid", "sensor", "platform", "processing", "daynight",
              "confidence_raw", "confidence_class", "version", "source_file"):
        if not _is_string_dtype(df[c].dtype):
            raise ContractError(f"detections: {c} must be string")
    if not (pd.api.types.is_datetime64_any_dtype(df["date_local"]) or df["date_local"].dtype == object):
        raise ContractError("detections: date_local must be a date")


def validate_celldays(df: pd.DataFrame) -> None:
    _require_columns(df, CELLDAYS_COLUMNS, "celldays")
    for c in ("cell_lat_idx", "cell_lon_idx", "n_detections"):
        if not pd.api.types.is_integer_dtype(df[c]):
            raise ContractError(f"celldays: {c} must be int32")
    if not pd.api.types.is_float_dtype(df["frp_sum"]):
        raise ContractError("celldays: frp_sum must be float64")
    if not (_is_string_dtype(df["tile_id"].dtype) and _is_string_dtype(df["platform"].dtype)):
        raise ContractError("celldays: tile_id/platform must be string")
    if not (pd.api.types.is_datetime64_any_dtype(df["date_local"]) or df["date_local"].dtype == object):
        raise ContractError("celldays: date_local must be a date")


def validate_calibration(df: pd.DataFrame) -> None:
    _require_columns(df, CALIBRATION_COLUMNS, "calibration")
    if not (_is_string_dtype(df["tile_id"].dtype) and _is_string_dtype(df["level"].dtype)):
        raise ContractError("calibration: tile_id/level must be string")
    if not pd.api.types.is_integer_dtype(df["month"]):
        raise ContractError("calibration: month must be int8")
    if not pd.api.types.is_float_dtype(df["k"]):
        raise ContractError("calibration: k must be float64")
    for c in ("modis_celldays", "viirs_celldays"):
        if not pd.api.types.is_integer_dtype(df[c]):
            raise ContractError(f"calibration: {c} must be int64")


def validate_harmonized(df: pd.DataFrame) -> None:
    _require_columns(df, HARMONIZED_COLUMNS, "harmonized_daily")
    for c in ("cell_lat_idx", "cell_lon_idx"):
        if not pd.api.types.is_integer_dtype(df[c]):
            raise ContractError(f"harmonized_daily: {c} must be int32")
    if not (_is_string_dtype(df["tile_id"].dtype) and _is_string_dtype(df["basis"].dtype)):
        raise ContractError("harmonized_daily: tile_id/basis must be string")
    if not pd.api.types.is_float_dtype(df["value"]):
        raise ContractError("harmonized_daily: value must be float64")
    if "sensor" in df.columns or "platform" in df.columns:
        raise ContractError("harmonized_daily: must not contain sensor or platform")
    if not (pd.api.types.is_datetime64_any_dtype(df["date_local"]) or df["date_local"].dtype == object):
        raise ContractError("harmonized_daily: date_local must be a date")