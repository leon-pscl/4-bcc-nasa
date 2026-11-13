import pandas as pd

from firecal.ingest.db import read_firms_csv


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
    from firecal.ingest.db import connect, ingest_files
    from firecal.config import Settings
    import pandas as pd
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path / "processed")
    p = tmp_path / "a.csv"
    p.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")
    con = connect()
    ingest_files(con, [str(p)], "test_region", (-180, -90, 180, 90), s)
    ingest_files(con, [str(p)], "test_region", (-180, -90, 180, 90), s)
    out = pd.read_parquet(s.DATA_PROCESSED + "/detections/region=test_region/year=2024")
    assert len(out) == 1


def test_sp_replaces_nrt(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    from firecal.config import Settings
    import pandas as pd
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path / "processed")
    nrt = tmp_path / "nrt.csv"
    nrt.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")
    sp = tmp_path / "sp.csv"
    sp.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1,3,1,D\n")
    con = connect()
    ingest_files(con, [str(nrt)], "test_region", (-180, -90, 180, 90), s)
    ingest_files(con, [str(sp)], "test_region", (-180, -90, 180, 90), s)
    out = pd.read_parquet(s.DATA_PROCESSED + "/detections/region=test_region/year=2024")
    assert set(out["processing"]) == {"SP"}
