import numpy as np
import pandas as pd

from firecal.contracts import (
    validate_detections, validate_celldays, validate_calibration,
    validate_harmonized, ContractError,
)


def _det_df():
    n = 3
    return pd.DataFrame({
        "uid": ["a", "b", "c"],
        "sensor": ["MODIS"] * n,
        "platform": ["Aqua"] * n,
        "processing": ["NRT"] * n,
        "latitude": np.array([1.0, 2.0, 3.0]),
        "longitude": np.array([1.0, 2.0, 3.0]),
        "acq_datetime_utc": pd.to_datetime(["2026-09-27T00:00:00"] * n),
        "date_local": pd.to_datetime(["2026-09-27"] * n).date,
        "daynight": ["D"] * n,
        "confidence_raw": ["80"] * n,
        "confidence_class": ["high"] * n,
        "frp": np.array([1.0, 2.0, 3.0]),
        "scan": np.array([1.0, 1.0, 1.0]),
        "track": np.array([1.0, 1.0, 1.0]),
        "brightness": np.array([300.0, 300.0, 300.0]),
        "bright_t31": np.array([290.0, 290.0, 290.0]),
        "type": pd.array([0, 0, 0], dtype="Int8"),
        "version": ["6.1NRT"] * n,
        "source_file": ["sample"] * n,
    })


def test_detections_valid():
    validate_detections(_det_df())


def test_detections_missing_column():
    df = _det_df().drop(columns=["frp"])
    try:
        validate_detections(df)
    except ContractError:
        return
    raise AssertionError("expected ContractError")


def test_detections_bad_dtype():
    df = _det_df()
    df["latitude"] = df["latitude"].astype(str)
    try:
        validate_detections(df)
    except ContractError:
        return
    raise AssertionError("expected ContractError")


def test_celldays_valid():
    df = pd.DataFrame({
        "cell_lat_idx": pd.array([1, 2, 3], dtype="int32"),
        "cell_lon_idx": pd.array([1, 2, 3], dtype="int32"),
        "tile_id": ["0_0"] * 3,
        "date_local": pd.to_datetime(["2026-09-27"] * 3).date,
        "platform": ["Aqua"] * 3,
        "n_detections": pd.array([1, 2, 3], dtype="int32"),
        "frp_sum": np.array([1.0, 2.0, 3.0]),
    })
    validate_celldays(df)


def test_calibration_valid():
    df = pd.DataFrame({
        "tile_id": ["0_0", "ALL"],
        "month": pd.array([8, 0], dtype="int8"),
        "k": np.array([1.5, 1.2]),
        "modis_celldays": pd.array([10, 100], dtype="int64"),
        "viirs_celldays": pd.array([15, 120], dtype="int64"),
        "level": ["tile_month", "all"],
    })
    validate_calibration(df)


def test_harmonized_rejects_sensor():
    df = pd.DataFrame({
        "cell_lat_idx": pd.array([1, 2], dtype="int32"),
        "cell_lon_idx": pd.array([1, 2], dtype="int32"),
        "tile_id": ["0_0", "0_0"],
        "date_local": pd.to_datetime(["2026-09-27", "2026-09-27"]).date,
        "value": np.array([1.0, 2.0]),
        "basis": ["viirs", "viirs"],
        "sensor": ["VIIRS", "VIIRS"],
    })
    try:
        validate_harmonized(df)
    except ContractError:
        return
    raise AssertionError("expected ContractError")


def test_harmonized_valid():
    df = pd.DataFrame({
        "cell_lat_idx": pd.array([1, 2], dtype="int32"),
        "cell_lon_idx": pd.array([1, 2], dtype="int32"),
        "tile_id": ["0_0", "0_0"],
        "date_local": pd.to_datetime(["2026-09-27", "2026-09-27"]).date,
        "value": np.array([1.0, 2.0]),
        "basis": ["viirs", "viirs"],
    })
    validate_harmonized(df)