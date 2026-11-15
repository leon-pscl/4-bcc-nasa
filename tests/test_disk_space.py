"""Disk-space fixes: ingest staging cleanup (3A) and leftover sweep (3B)."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

CSV_HEADER = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
              "instrument,confidence,version,bright_t31,frp,daynight\n")
CSV_ROW = ("1,2,3,1,1,2024-01-01,100,A,Aqua,50,6.1NRT,3,1,D\n")
CSV_ROW2 = ("1,2,3,1,1,2024-01-01,200,A,Aqua,50,6.1NRT,3,1,D\n")


def _settings(tmp_path):
    from firecal.config import Settings
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path / "processed")
    s.DUCKDB_TEMP_DIR = str(tmp_path / "duckdb_tmp")
    return s


def _csv(tmp_path, name, rows=(CSV_ROW,)):
    p = tmp_path / name
    p.write_text(CSV_HEADER + "".join(rows))
    return str(p)


def _staging_leftovers(settings, region):
    root = Path(settings.DATA_PROCESSED) / "_staging" / region
    if not root.is_dir():
        return []
    return list(root.rglob("_part_*"))


def test_ingest_removes_staging_and_counts_rows(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    s = _settings(tmp_path)
    f1 = _csv(tmp_path, "a.csv")
    f2 = _csv(tmp_path, "b.csv", rows=(CSV_ROW, CSV_ROW2))
    con = connect()
    written, rows = ingest_files(con, [f1, f2], "test_region", (-180, -90, 180, 90), s)
    assert _staging_leftovers(s, "test_region") == []
    assert rows == 3
    out = pd.read_parquet(s.DATA_PROCESSED + "/detections/region=test_region/year=2024")
    assert len(out) == 3


def test_ingest_dry_run_removes_staging(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    s = _settings(tmp_path)
    f1 = _csv(tmp_path, "a.csv")
    con = connect()
    ingest_files(con, [f1], "test_region", (-180, -90, 180, 90), s, dry_run=True)
    assert _staging_leftovers(s, "test_region") == []


def test_ingest_failure_removes_staging_and_keeps_state(tmp_path, monkeypatch):
    from firecal.ingest.db import connect, ingest_files
    import firecal.ingest.db as ingest_db
    from firecal.dataset import save_state

    s = _settings(tmp_path)
    save_state(s, {"files": {"already": 1}})
    before = Path(s.DATA_PROCESSED, "_state.json").read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("write_partition blew up")

    monkeypatch.setattr(ingest_db, "write_partition", boom)
    f1 = _csv(tmp_path, "a.csv")
    con = connect()
    with pytest.raises(RuntimeError, match="blew up"):
        ingest_files(con, [f1], "test_region", (-180, -90, 180, 90), s)
    assert _staging_leftovers(s, "test_region") == []
    assert Path(s.DATA_PROCESSED, "_state.json").read_bytes() == before


def test_ingest_state_has_no_staging_key(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    from firecal.dataset import load_state
    s = _settings(tmp_path)
    f1 = _csv(tmp_path, "a.csv")
    con = connect()
    ingest_files(con, [f1], "test_region", (-180, -90, 180, 90), s)
    state = load_state(s)
    assert all("staging" not in e for e in state.get("files", {}).values())


def test_duckdb_temp_dir_guard(tmp_path):
    from firecal.dataset import validate_duckdb_temp_dir
    s = _settings(tmp_path)
    s.DATA_RAW = str(tmp_path / "raw")
    s.DATA_PROCESSED = str(tmp_path / "processed")

    ok = tmp_path / "duckdb_tmp"
    s.DUCKDB_TEMP_DIR = str(ok)  # contains "duckdb", not inside/above data
    validate_duckdb_temp_dir(s)  # must not raise
    s.DUCKDB_TEMP_DIR = "/tmp/duckdb"
    validate_duckdb_temp_dir(s)  # accepted

    refused = [
        "/",
        os.path.realpath("/"),          # filesystem root (drive root on Windows)
        "/tmp",
        str(Path.home()),
        s.DATA_RAW,
        s.DATA_PROCESSED,
        str(Path(s.DATA_RAW) / "sub" / "duckdb"),        # inside DATA_RAW
        str(Path(s.DATA_PROCESSED) / "duckdb"),          # inside DATA_PROCESSED
        str(Path(s.DATA_RAW).parent) ,                   # above DATA_RAW (tmp_path)
        str(Path(s.DATA_PROCESSED).parent),              # above DATA_PROCESSED
        str(tmp_path / "spill"),                         # last name lacks "duckdb"
    ]
    for bad in refused:
        s.DUCKDB_TEMP_DIR = bad
        with pytest.raises(SystemExit) as exc:
            validate_duckdb_temp_dir(s)
        assert "DUCKDB_TEMP_DIR" in str(exc.value)


def test_sweep_removes_leftovers_and_keeps_partitions(tmp_path):
    from firecal.dataset import sweep_leftovers
    s = _settings(tmp_path)
    root = Path(s.DATA_PROCESSED)

    # published partition that must survive
    part = root / "detections" / "region=x" / "year=2024"
    part.mkdir(parents=True)
    pd.DataFrame({"a": [1, 2]}).to_parquet(part / "data_0.parquet", index=False)

    # planted leftovers: one of each
    ds_part = root / "detections" / "_part_abc123"
    ds_part.mkdir()
    (ds_part / "x.parquet").write_bytes(b"x" * 100)
    top_part = root / "_part_top"
    top_part.mkdir()
    (top_part / "y.parquet").write_bytes(b"y" * 100)
    staging = root / "_staging" / "southeast_asia" / "_part_zzz"
    staging.mkdir(parents=True)
    (staging / "s.parquet").write_bytes(b"s" * 100)
    (root / "_state.json.tmp").write_bytes(b"tmp" * 100)
    stray_tmp = root / "validation" / "x.tmp"
    stray_tmp.parent.mkdir()
    stray_tmp.write_bytes(b"t" * 100)
    temp = Path(s.DUCKDB_TEMP_DIR)
    temp.mkdir()
    (temp / "spill_0.tmp").write_bytes(b"spill" * 100)

    logs = []
    removed, freed = sweep_leftovers(s, log=logs.append)

    assert not ds_part.exists()
    assert not top_part.exists()
    assert not (root / "_staging").exists()
    assert not (root / "_state.json.tmp").exists()
    assert not stray_tmp.exists()
    assert list(temp.iterdir()) == []
    assert (part / "data_0.parquet").exists()
    assert pd.read_parquet(part / "data_0.parquet")["a"].tolist() == [1, 2]
    assert removed >= 6
    assert freed >= 600
    assert any("GB" in line for line in logs)
