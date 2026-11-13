"""Integrity checks for the pipeline: the duplicates bug must never pass silently.

(a) calibration: one row per (region, platform, reference, tile_id, month)
(b) harmonized_daily: one row per (region, cell_lat_idx, cell_lon_idx, date_local)
(c) rebuild twice -> identical row counts
"""

import os
import shutil

import pandas as pd
import pytest

from firecal.config import Settings


def _sample_csv(tmp_path, name, rows):
    p = tmp_path / name
    cols = ["latitude", "longitude", "brightness", "scan", "track", "acq_date",
            "acq_time", "satellite", "instrument", "confidence", "version",
            "bright_t31", "frp", "daynight"]
    with open(p, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    return p


def _row(lat, lon, date, time=100, sat="A", conf=50):
    return [lat, lon, 300.0, 1.0, 1.0, date, time, sat, "MODIS", conf,
            "6.1NRT", 300.0, 5.0, "D"]


def _settings(tmp_path):
    s = Settings()
    s.DATA_RAW = str(tmp_path / "raw")
    s.DATA_PROCESSED = str(tmp_path / "processed")
    s.CALIBRATION_YEARS = (2015, 2016)
    s.VALIDATION_YEARS = (2017, 2018)
    return s


def _build(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    from firecal.cells.db import rebuild as rebuild_cells
    from firecal.harmonize.db import rebuild

    settings = _settings(tmp_path)
    rows = []
    for year in (2015, 2016, 2017, 2018):
        for day in range(1, 20):
            rows.append(_row(0.0, 112.0, f"{year}-09-{day:02d}", sat="A"))
            rows.append(_row(0.0, 112.0, f"{year}-09-{day:02d}", sat="N"))
    csv = _sample_csv(tmp_path, "a.csv", rows)
    con = connect()
    ingest_files(con, [str(csv)], "testreg", (-180.0, -90.0, 180.0, 90.0), settings)
    rebuild_cells(settings, region="testreg")
    rebuilt = rebuild(settings, region="testreg")
    assert rebuilt, "rebuild should write partitions (state was empty)"
    return settings


def test_calibration_unique(tmp_path):
    settings = _build(tmp_path)
    df = pd.read_parquet(os.path.join(settings.DATA_PROCESSED, "calibration.parquet"))
    assert not df.empty
    dup = df.groupby(["region", "platform", "reference", "tile_id", "month"]).size()
    assert (dup <= 1).all(), f"calibration has duplicates:\n{dup[dup > 1]}"


def test_harmonized_unique(tmp_path):
    import duckdb
    settings = _build(tmp_path)
    root = os.path.join(settings.DATA_PROCESSED, "harmonized_daily")
    con = duckdb.connect()
    n, nd = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT (region, cell_lat_idx, cell_lon_idx, date_local)) "
        f"FROM read_parquet('{root.replace(os.sep, '/')}/region=testreg/*/*.parquet')"
    ).fetchone()
    assert n == nd, f"harmonized has duplicate rows: {n} rows, {nd} distinct (cell, date)"


def test_rebuild_idempotent(tmp_path):
    import duckdb
    from firecal.harmonize.db import rebuild
    settings = _build(tmp_path)
    root = os.path.join(settings.DATA_PROCESSED, "harmonized_daily")

    def counts():
        con = duckdb.connect()
        return con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{root.replace(os.sep, '/')}/region=testreg/*/*.parquet')"
        ).fetchone()[0]

    first = counts()
    rebuilt = rebuild(settings, region="testreg")
    assert rebuilt == [], "second rebuild should be a no-op (fingerprint unchanged)"
    assert counts() == first


def test_harmonized_staging_failure_keeps_old_partition_and_state(tmp_path, monkeypatch):
    """Harmonized check (b) runs on the staging copy before any swap: a duplicate
    row must not reach the parquet partitions, and state must not be updated."""
    settings = _build(tmp_path)   # builds good partitions first
    import pandas as pd
    from firecal import harmonize
    from firecal.dataset import load_state, save_state

    part = os.path.join(settings.DATA_PROCESSED, "harmonized_daily",
                        "region=testreg", "year=2015")
    before_files = {f: open(os.path.join(part, f), "rb").read()
                    for f in os.listdir(part) if f.endswith(".parquet")}
    assert before_files

    # force every partition to rebuild: wipe the harmonized fingerprints
    state = load_state(settings)
    state["harmonized_daily"] = {}
    save_state(settings, state)
    before_state = open(os.path.join(settings.DATA_PROCESSED, "_state.json"), "rb").read()

    # inject a duplicate (cell, date) pair into the harmonized SQL
    orig = harmonize.db.harmonized_sql

    def dup_harmonized_sql(cd, cal_rel, series_start, switch_date):
        base = orig(cd, cal_rel, series_start, switch_date)
        return f"SELECT * FROM ({base}) UNION ALL (SELECT * FROM ({base}) LIMIT 1)"

    monkeypatch.setattr(harmonize.db, "harmonized_sql", dup_harmonized_sql)
    with pytest.raises(AssertionError):
        harmonize.db.rebuild(settings, region="testreg")

    # the old partition is unchanged
    assert set(os.listdir(part)) == set(before_files)
    for f, blob in before_files.items():
        assert open(os.path.join(part, f), "rb").read() == blob
    # state file not updated by the failed rebuild
    assert open(os.path.join(settings.DATA_PROCESSED, "_state.json"), "rb").read() == before_state
    # no staging leftovers
    assert list((tmp_path / "processed" / "harmonized_daily").glob("_part_*")) == []


def test_writer_lock_blocks_second_process(tmp_path):
    """While one process holds the OS writer lock, a second process exits."""
    import subprocess
    import sys
    from firecal.dataset import acquire_writer_lock, release_writer_lock
    from firecal.config import Settings

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path)
    s.DATA_RAW = str(tmp_path / "raw")
    fd = acquire_writer_lock(s)
    try:
        code = (
            "import sys\n"
            f"sys.path.insert(0, {repo!r})\n"
            "from firecal.config import Settings\n"
            "from firecal.dataset import acquire_writer_lock\n"
            "s = Settings()\n"
            f"s.DATA_PROCESSED = {str(tmp_path)!r}\n"
            f"s.DATA_RAW = {str(tmp_path / 'raw')!r}\n"
            "acquire_writer_lock(s)\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           cwd=repo)
        out = r.stdout + r.stderr
        assert r.returncode != 0
        assert "only one writer" in out or "another pipeline process" in out
    finally:
        release_writer_lock(fd)


def test_writer_lock_released(tmp_path):
    """After release, the next process can take the lock."""
    import subprocess
    import sys
    from firecal.dataset import acquire_writer_lock, release_writer_lock
    from firecal.config import Settings

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    s = Settings()
    s.DATA_PROCESSED = str(tmp_path)
    s.DATA_RAW = str(tmp_path / "raw")
    fd = acquire_writer_lock(s)
    release_writer_lock(fd)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repo!r})\n"
        "from firecal.config import Settings\n"
        "from firecal.dataset import acquire_writer_lock, release_writer_lock\n"
        "s = Settings()\n"
        f"s.DATA_PROCESSED = {str(tmp_path)!r}\n"
        "fd = acquire_writer_lock(s)\n"
        "release_writer_lock(fd)\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=repo)
    assert "ok" in r.stdout
