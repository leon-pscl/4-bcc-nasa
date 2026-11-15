"""C1 slim: uid is derived at ingest for dedup only, never stored; the migration drops it."""

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "migrate_c1_slim.py"

CSV = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
       "instrument,confidence,version,bright_t31,frp,daynight\n"
       "1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")


def _settings(tmp_path):
    from firecal.config import Settings
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path / "processed")
    s.DUCKDB_TEMP_DIR = str(tmp_path / "duckdb")
    return s


def test_ingest_publishes_partition_without_uid(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    s = _settings(tmp_path)
    f = tmp_path / "a.csv"
    f.write_text(CSV)
    ingest_files(connect(), [str(f)], "test_region", (-180, -90, 180, 90), s)
    out = pd.read_parquet(s.DATA_PROCESSED + "/detections/region=test_region/year=2024")
    assert "uid" not in out.columns
    assert len(out) == 1
    keys = list(zip(out["date_local"], out["platform"], out["latitude"], out["longitude"]))
    assert keys == sorted(keys)


def test_sp_still_replaces_nrt_without_stored_uid(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    s = _settings(tmp_path)
    nrt = tmp_path / "nrt.csv"
    nrt.write_text(CSV)
    sp = tmp_path / "sp.csv"
    sp.write_text(CSV.replace("6.1NRT", "6.1"))
    con = connect()
    ingest_files(con, [str(nrt)], "test_region", (-180, -90, 180, 90), s)
    ingest_files(con, [str(sp)], "test_region", (-180, -90, 180, 90), s)
    out = pd.read_parquet(s.DATA_PROCESSED + "/detections/region=test_region/year=2024")
    assert set(out["processing"]) == {"SP"}
    assert len(out) == 1


def _make_fat_partition(s):
    part = Path(s.DATA_PROCESSED) / "detections" / "region=test_region" / "year=2024"
    part.mkdir(parents=True)
    pd.DataFrame({
        "uid": pd.array([f"{i:032x}" for i in range(7)], dtype="string"),
        "sensor": pd.array(["MODIS"] * 7, dtype="string"),
        "platform": pd.array(["Aqua"] * 7, dtype="string"),
        "processing": pd.array(["SP"] * 7, dtype="string"),
        "latitude": [1.0 + i for i in range(7)],
        "longitude": [2.0] * 7,
        "acq_datetime_utc": pd.to_datetime(["2024-01-01"] * 7),
        "date_local": [pd.Timestamp("2024-01-01").date()] * 7,
        "daynight": pd.array(["D"] * 7, dtype="string"),
        "confidence_raw": pd.array(["50"] * 7, dtype="string"),
        "confidence_class": pd.array(["nominal"] * 7, dtype="string"),
        "frp": [1.0] * 7,
        "scan": [1.0] * 7,
        "track": [1.0] * 7,
        "brightness": [1.0] * 7,
        "bright_t31": [1.0] * 7,
        "type": pd.array([0] * 7, dtype="Int8"),
        "version": pd.array(["6.1"] * 7, dtype="string"),
        "source_file": pd.array(["x"] * 7, dtype="string"),
    }).to_parquet(part / "data_0.parquet", index=False)
    return part


def _run_migration(tmp_path, *argv):
    env = dict(os.environ)
    env["DATA_PROCESSED"] = str(tmp_path / "processed")
    env["DATA_RAW"] = str(tmp_path / "raw")
    env["DUCKDB_TEMP_DIR"] = str(tmp_path / "duckdb")
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, str(SCRIPT), *argv],
                          capture_output=True, text=True, cwd=str(tmp_path), env=env)


def test_migration_dry_run_keeps_files(tmp_path):
    s = _settings(tmp_path)
    part = _make_fat_partition(s)
    before = (part / "data_0.parquet").read_bytes()
    r = _run_migration(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "PLAN" in r.stdout
    assert (part / "data_0.parquet").read_bytes() == before


def test_migration_apply_drops_uid_and_is_idempotent(tmp_path):
    s = _settings(tmp_path)
    part = _make_fat_partition(s)
    r = _run_migration(tmp_path, "--apply")
    assert r.returncode == 0, r.stderr
    out = pd.read_parquet(part / "data_0.parquet")
    assert "uid" not in out.columns
    assert len(out) == 7
    r2 = _run_migration(tmp_path, "--apply")
    assert r2.returncode == 0, r2.stderr
    assert "SKIP" in r2.stdout
    assert len(pd.read_parquet(part / "data_0.parquet")) == 7


def test_migration_refuses_nothing_on_empty_dataset(tmp_path):
    (Path(tmp_path) / "processed" / "detections").mkdir(parents=True)
    r = _run_migration(tmp_path, "--apply")
    assert r.returncode == 0, r.stderr
    assert "partitions to migrate: 0" in r.stdout


def _load_script_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("migrate_c1_slim", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_corrupted_staged_partition_is_refused(tmp_path):
    # the content check must reject a staged copy whose rows/values differ,
    # and write_partition must then leave the published partition untouched
    from firecal.duck import connect
    from firecal.config import Settings
    from firecal.dataset import write_partition, dataset_dir, DETECTIONS
    s = _settings(tmp_path)
    _make_fat_partition(s)
    part = Path(s.DATA_PROCESSED) / "detections" / "region=test_region" / "year=2024"
    before_bytes = (part / "data_0.parquet").read_bytes()

    mod = _load_script_module()
    con = connect(s, "pipeline")
    glob = str(part / "*.parquet").replace("\\", "/")
    slim = f"SELECT * EXCLUDE (uid) FROM read_parquet('{glob}')"
    before_check = con.execute(
        f"SELECT COUNT(*), SUM(hash(platform, latitude, longitude, acq_datetime_utc, frp, "
        f"confidence_raw, type)) FROM ({slim})").fetchone()

    # corrupted "rewrite": drop one row and flip another value
    corrupt = f"SELECT * EXCLUDE (uid) FROM read_parquet('{glob}') WHERE latitude > 3.0"
    with pytest.raises(ValueError, match="content check"):
        write_partition(con, corrupt, s, DETECTIONS, "test_region", 2024,
                        post_check=mod.make_post_check(before_check, "test_region", 2024))
    assert (part / "data_0.parquet").read_bytes() == before_bytes


def test_sorted_partition_after_migration(tmp_path):
    s = _settings(tmp_path)
    _make_fat_partition(s)
    r = _run_migration(tmp_path, "--apply")
    assert r.returncode == 0, r.stderr
    out = pd.read_parquet(Path(s.DATA_PROCESSED) / "detections" / "region=test_region" / "year=2024")
    keys = list(zip(out["date_local"], out["platform"], out["latitude"], out["longitude"]))
    assert keys == sorted(keys)
