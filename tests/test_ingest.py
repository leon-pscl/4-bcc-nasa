import pandas as pd

from firecal.ingest.firms_csv import read_firms_csv
from firecal.ingest.store import merge_into_store


def test_header_only_returns_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n")
    df = read_firms_csv(str(p))
    assert len(df) == 0
    assert "uid" in df.columns


def test_unknown_satellite_raises(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,100,X,MODIS,50,6.1NRT,3,1,D\n")
    try:
        read_firms_csv(str(p))
    except ValueError as e:
        assert "unknown satellite" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_viirs_columns_renamed(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n1,2,3,1,1,2024-01-01,100,N,VIIRS, n,2.0NRT,4,1,D\n")
    df = read_firms_csv(str(p))
    assert "brightness" in df.columns
    assert "bright_t31" in df.columns


def test_negative_coords(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n-17.5,-63.2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")
    df = read_firms_csv(str(p))
    assert df.iloc[0]["latitude"] < 0


def test_acq_time_parsing(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,18,A,Aqua,50,6.1NRT,3,1,D\n1,2,3,1,1,2024-01-01,1947,A,Aqua,50,6.1NRT,3,1,D\n")
    df = read_firms_csv(str(p))
    assert df.iloc[0]["acq_datetime_utc"].hour == 0
    assert df.iloc[0]["acq_datetime_utc"].minute == 18
    assert df.iloc[1]["acq_datetime_utc"].hour == 19
    assert df.iloc[1]["acq_datetime_utc"].minute == 47


def test_idempotent_merge(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")
    store = str(tmp_path / "store.parquet")
    df = read_firms_csv(str(p))
    merge_into_store(df, store)
    merge_into_store(df, store)
    out = pd.read_parquet(store)
    assert len(out) == 1


def test_sp_replaces_nrt():
    # build two frames
    import tempfile, os
    from datetime import date
    import pandas as pd
    modis_nrt = pd.DataFrame({
        "uid": ["u1"], "sensor": ["MODIS"], "platform": ["Aqua"], "processing": ["NRT"],
        "latitude": [1.0], "longitude": [2.0],
        "acq_datetime_utc": pd.to_datetime(["2024-01-01 10:00"]),
        "date_local": [date(2024,1,1)], "daynight": ["D"], "confidence_raw": ["50"],
        "confidence_class": ["nominal"], "frp": [1.0], "scan": [1.0], "track": [1.0],
        "brightness": [1.0], "bright_t31": [1.0], "type": pd.array([0], dtype="Int8"),
        "version": ["6.1NRT"], "source_file": ["x"],
    })
    modis_sp = modis_nrt.copy()
    modis_sp["processing"] = "SP"
    modis_sp["version"] = "6.1"
    from firecal.contracts import validate_detections
    validate_detections(modis_nrt)
    validate_detections(modis_sp)
    # same uid
    assert modis_nrt.iloc[0]["uid"] == modis_sp.iloc[0]["uid"]
    tmp = tempfile.mkdtemp()
    store = os.path.join(tmp, "s.parquet")
    merge_into_store(modis_nrt, store)
    merge_into_store(modis_sp, store)
    out = pd.read_parquet(store)
    assert set(out["processing"]) == {"SP"}