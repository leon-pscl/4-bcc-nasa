import pandas as pd

from firecal.contracts import validate_detections, validate_harmonized


def _good_detections():
    return pd.DataFrame({
        "uid": pd.array(["a"], dtype="string"),
        "sensor": pd.array(["MODIS"], dtype="string"),
        "platform": pd.array(["Aqua"], dtype="string"),
        "processing": pd.array(["NRT"], dtype="string"),
        "latitude": [1.0],
        "longitude": [2.0],
        "acq_datetime_utc": pd.to_datetime(["2024-01-01"]),
        "date_local": [pd.Timestamp("2024-01-01").date()],
        "daynight": pd.array(["D"], dtype="string"),
        "confidence_raw": pd.array(["50"], dtype="string"),
        "confidence_class": pd.array(["nominal"], dtype="string"),
        "frp": [1.0],
        "scan": [1.0],
        "track": [1.0],
        "brightness": [1.0],
        "bright_t31": [1.0],
        "type": pd.array([0], dtype="Int8"),
        "version": pd.array(["6.1NRT"], dtype="string"),
        "source_file": pd.array(["x"], dtype="string"),
    })


def test_good_detections_passes():
    validate_detections(_good_detections())


def test_missing_column_fails():
    df = _good_detections().drop(columns=["uid"])
    try:
        validate_detections(df)
    except ValueError as e:
        assert "missing columns" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_wrong_dtype_fails():
    df = _good_detections().copy()
    df["latitude"] = df["latitude"].astype("int64")
    try:
        validate_detections(df)
    except ValueError as e:
        assert "latitude" in str(e)
    else:
        raise AssertionError("expected ValueError")


def _good_harmonized():
    return pd.DataFrame({
        "region": pd.array(["test_region"], dtype="string"),
        "cell_lat_idx": pd.array([1], dtype="int32"),
        "cell_lon_idx": pd.array([2], dtype="int32"),
        "tile_id": pd.array(["0_0"], dtype="string"),
        "date_local": [pd.Timestamp("2024-01-01").date()],
        "value": [1.0],
        "basis": pd.array(["viirs"], dtype="string"),
    })


def test_good_harmonized_passes():
    validate_harmonized(_good_harmonized())


def test_sensor_column_in_c4_fails():
    df = _good_harmonized().copy()
    df["sensor"] = pd.array(["MODIS"], dtype="string")
    try:
        validate_harmonized(df)
    except ValueError as e:
        assert "sensor" in str(e)
    else:
        raise AssertionError("expected ValueError")


def _good_celldays():
    return pd.DataFrame({
        "cell_lat_idx": pd.array([1], dtype="int32"),
        "cell_lon_idx": pd.array([2], dtype="int32"),
        "tile_id": pd.array(["0_0"], dtype="string"),
        "date_local": [pd.Timestamp("2024-01-01").date()],
        "platform": pd.array(["Aqua"], dtype="string"),
        "n_detections": pd.array([3], dtype="int32"),
        "frp_sum": [1.5],
    })


def test_good_celldays_passes():
    from firecal.contracts import validate_celldays
    validate_celldays(_good_celldays())


def test_celldays_missing_column_fails():
    from firecal.contracts import validate_celldays
    df = _good_celldays().drop(columns=["tile_id"])
    try:
        validate_celldays(df)
    except ValueError as e:
        assert "missing columns" in str(e)
    else:
        raise AssertionError("expected ValueError")


def _good_calibration():
    return pd.DataFrame({
        "region": pd.array(["test_region"], dtype="string"),
        "platform": pd.array(["Aqua"], dtype="string"),
        "reference": pd.array(["SNPP"], dtype="string"),
        "tile_id": pd.array(["0_0"], dtype="string"),
        "month": pd.array([1], dtype="int8"),
        "k": [1.5],
        "modis_celldays": [10],
        "viirs_celldays": [15],
        "level": pd.array(["tile_month"], dtype="string"),
    })


def test_good_calibration_passes():
    from firecal.contracts import validate_calibration
    validate_calibration(_good_calibration())


def test_calibration_wrong_dtype_fails():
    from firecal.contracts import validate_calibration
    df = _good_calibration().copy()
    df["month"] = df["month"].astype("int64")
    try:
        validate_calibration(df)
    except ValueError as e:
        assert "month" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_date_local_must_be_date():
    from firecal.contracts import validate_celldays
    df = _good_celldays().copy()
    df["date_local"] = ["not-a-date"]
    try:
        validate_celldays(df)
    except ValueError as e:
        assert "date_local" in str(e)
    else:
        raise AssertionError("expected ValueError")
def test_basis_validator():
    from firecal.contracts import validate_harmonized
    import pandas as pd
    for b in ("viirs", "viirs_noaa20", "viirs_noaa21", "modis_scaled", "modis_gapfill"):
        df = pd.DataFrame({
            "region": pd.array(["x"], dtype="string"),
            "cell_lat_idx": pd.array([1], dtype="int32"),
            "cell_lon_idx": pd.array([2], dtype="int32"),
            "tile_id": pd.array(["0_0"], dtype="string"),
            "date_local": [pd.Timestamp("2024-01-01").date()],
            "value": [1.0],
            "basis": pd.array([b], dtype="string"),
        })
        validate_harmonized(df)


def test_basis_validator_rejects_unknown():
    from firecal.contracts import validate_harmonized
    import pandas as pd
    df = pd.DataFrame({
        "region": pd.array(["x"], dtype="string"),
        "cell_lat_idx": pd.array([1], dtype="int32"),
        "cell_lon_idx": pd.array([2], dtype="int32"),
        "tile_id": pd.array(["0_0"], dtype="string"),
        "date_local": [pd.Timestamp("2024-01-01").date()],
        "value": [1.0],
        "basis": pd.array(["bogus"], dtype="string"),
    })
    try:
        validate_harmonized(df)
    except ValueError as e:
        assert "basis" in str(e)
    else:
        raise AssertionError("expected ValueError")
