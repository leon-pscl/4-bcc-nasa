"""Tests for the DuckDB pipeline: partitions, incremental rebuilds, data version."""

import os
import shutil

import pandas as pd
import pytest

from firecal.config import Settings
from firecal.dataset import (CELLDAYS, DETECTIONS, HARMONIZED, data_version,
                             load_state, partitions_of, write_data_versions)


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


def _settings(tmp_path):
    s = Settings()
    s.DATA_RAW = str(tmp_path / "raw")
    s.DATA_PROCESSED = str(tmp_path / "processed")
    return s


def _row(lat, lon, date, time=100, sat="A", conf=50):
    return [lat, lon, 300.0, 1.0, 1.0, date, time, sat, "MODIS", conf,
            "6.1NRT", 300.0, 5.0, "D"]


def test_ingest_writes_region_year_partitions(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    settings = _settings(tmp_path)
    csv = _sample_csv(tmp_path, "a.csv", [_row(0.0, 112.0, "2015-09-10"),
                                          _row(0.0, 112.0, "2019-09-10")])
    con = connect()
    written, rows = ingest_files(con, [str(csv)], "southeast_asia",
                                  (92, -11, 141, 28.5), settings)
    assert rows == 2
    assert sorted(written) == ["southeast_asia/2015", "southeast_asia/2019"]
    parts = partitions_of(settings, DETECTIONS)
    assert "southeast_asia/2015" in parts
    assert "southeast_asia/2019" in parts


def test_two_regions_write_separate_partitions(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    settings = _settings(tmp_path)
    a = _sample_csv(tmp_path, "a.csv", [_row(0.0, 112.0, "2015-09-10")])
    b = _sample_csv(tmp_path, "b.csv", [_row(-16.0, -62.0, "2015-09-10")])
    con = connect()
    ingest_files(con, [str(a)], "southeast_asia", (92, -11, 141, 28.5), settings)
    ingest_files(con, [str(b)], "amazon", (-80, -20, -44, 6), settings)
    parts = partitions_of(settings, DETECTIONS)
    assert "southeast_asia/2015" in parts
    assert "amazon/2015" in parts


def test_incremental_rebuild_only_changed_year(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    settings = _settings(tmp_path)
    csv = _sample_csv(tmp_path, "a.csv", [_row(0.0, 112.0, "2015-09-10"),
                                          _row(0.0, 112.0, "2019-09-10")])
    con = connect()
    ingest_files(con, [str(csv)], "southeast_asia", (92, -11, 141, 28.5), settings)
    # same file again: nothing to do
    written, _ = ingest_files(con, [str(csv)], "southeast_asia",
                              (92, -11, 141, 28.5), settings)
    assert written == []
    # a changed file (new year) rebuilds only that year
    csv2 = _sample_csv(tmp_path, "b.csv", [_row(0.0, 112.0, "2020-09-10")])
    written, _ = ingest_files(con, [str(csv2)], "southeast_asia",
                              (92, -11, 141, 28.5), settings)
    assert written == ["southeast_asia/2020"]


def test_data_version_changes_with_content(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    settings = _settings(tmp_path)
    csv = _sample_csv(tmp_path, "a.csv", [_row(0.0, 112.0, "2015-09-10")])
    con = connect()
    ingest_files(con, [str(csv)], "southeast_asia", (92, -11, 141, 28.5), settings)
    v1 = data_version(settings, DETECTIONS)
    csv2 = _sample_csv(tmp_path, "b.csv", [_row(0.0, 112.0, "2016-09-10")])
    ingest_files(con, [str(csv2)], "southeast_asia", (92, -11, 141, 28.5), settings)
    v2 = data_version(settings, DETECTIONS)
    assert v1 != v2
    versions = write_data_versions(settings, [DETECTIONS])
    assert os.path.exists(os.path.join(settings.DATA_PROCESSED, "data_version.json"))
    assert DETECTIONS in versions


def test_cells_and_harmonize_write_partitions(tmp_path):
    from firecal.ingest.db import connect, ingest_files
    from firecal.cells.db import rebuild as rebuild_cells
    from firecal.harmonize.db import rebuild as rebuild_harmonize
    settings = _settings(tmp_path)
    settings.CALIBRATION_YEARS = (2015, 2016)
    settings.VALIDATION_YEARS = (2017, 2018)
    rows = []
    for year in (2015, 2016, 2017, 2018):
        for day in range(1, 20):
            rows.append(_row(0.0, 112.0, f"{year}-09-{day:02d}", sat="A"))
            rows.append(_row(0.0, 112.0, f"{year}-09-{day:02d}", sat="N"))
    csv = _sample_csv(tmp_path, "a.csv", rows)
    con = connect()
    ingest_files(con, [str(csv)], "southeast_asia", (92, -11, 141, 28.5), settings)
    rebuilt = rebuild_cells(settings, region="southeast_asia")
    assert rebuilt
    assert "southeast_asia/2015" in partitions_of(settings, CELLDAYS)
    rebuilt = rebuild_harmonize(settings, region="southeast_asia")
    assert rebuilt
    assert "southeast_asia/2015" in partitions_of(settings, HARMONIZED)
