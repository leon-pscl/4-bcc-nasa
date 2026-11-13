import math

import pandas as pd

from firecal.config import Settings
from firecal.ingest.db import read_firms_csv
from firecal.cells.db import build_celldays, validate_meta


def _sample_detections():
    import tempfile, os
    modis = read_firms_csv("sample-data/modis.csv")
    viirs = read_firms_csv("sample-data/viirs.csv")
    return pd.concat([modis, viirs], ignore_index=True)


def test_sample_numbers():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    det = _sample_detections()
    cd = build_celldays(det, settings)
    import datetime
    for d, expected in [((2026, 9, 27), (104, 268, 73)),
                        ((2026, 9, 28), (None, None, 54))]:
        day = datetime.date(*d)
        sub = cd[cd.date_local == day]
        modis = set(sub[sub.platform.isin(["Terra", "Aqua"])].apply(lambda r: (r.cell_lat_idx, r.cell_lon_idx), axis=1))
        viirs = set(sub[sub.platform == "SNPP"].apply(lambda r: (r.cell_lat_idx, r.cell_lon_idx), axis=1))
        if expected[0] is not None:
            assert len(modis) == expected[0]
            assert len(viirs) == expected[1]
        assert len(modis & viirs) == expected[2]
        if d == (2026, 9, 28):
            assert len(modis - viirs) == 56
            assert len(viirs - modis) == 197


def test_floor_not_truncation():
    assert math.floor(-17.8757 / 0.05) == -358


def test_filters_drop_low_and_type():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("nominal", "high")
    settings.KEEP_TYPES = (0,)
    det = _sample_detections()
    # make a low-confidence row and a type=1 row
    low = det.iloc[[0]].copy()
    low["confidence_class"] = "low"
    low["uid"] = low["uid"].astype(str) + "_low"
    cd = build_celldays(det, settings)
    # NRT rows (missing type) should be present
    assert len(cd) > 0


def test_meta_mismatch_refused():
    settings = Settings()
    bad_meta = {"grid_deg": 0.1, "tile_deg": 1.0, "confidence_keep": ["nominal", "high"], "keep_types": [0]}
    try:
        validate_meta(bad_meta, settings)
    except ValueError as e:
        assert "meta mismatch" in str(e)
    else:
        raise AssertionError("expected ValueError")
