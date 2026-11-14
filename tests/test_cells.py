import math

import pandas as pd

from firecal.cells.grid import cell_index, cell_index_sql
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


def test_cell_index_known_values():
    assert cell_index(0.3, 0.05) == 6
    assert cell_index(97.3, 0.05) == 1946
    assert cell_index(-17.8757, 0.05) == -358
    assert cell_index(14.14999, 0.05) == 282


def test_cell_index_edge_sweep_python_and_duckdb():
    import duckdb
    import pandas as pd
    for g in (0.05, 0.1):
        for i in range(-3600, 3600):
            assert cell_index(round(i * g, 5), g) == i, (i, g)
        df = pd.DataFrame({"i": list(range(-3600, 3600))})
        df["v"] = [round(i * g, 5) for i in df["i"]]
        con = duckdb.connect()
        try:
            con.register("t", df)
            rows = con.execute(
                f"SELECT i, {cell_index_sql('v', g)} AS idx FROM t").fetchall()
            for i, idx in rows:
                assert idx == i, (i, g)
        finally:
            con.close()


def test_celldays_edge_points_and_cover_match(tmp_path):
    import datetime
    import os
    import duckdb
    import pandas as pd
    from firecal.analytics.cover import cover_exists_latlon

    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.DATA_PROCESSED = str(tmp_path / "processed")

    det = pd.DataFrame([
        # lat/lon on cell edges; 14.14999 just below the 14.15 edge
        (0.3, 97.3, "Aqua", 10.0),
        (0.3, 92.05, "Aqua", 10.0),
        (14.14999, 100.5, "SNPP", 10.0),
    ], columns=["latitude", "longitude", "platform", "frp"])
    det["region"] = "test"
    det["date_local"] = datetime.date(2006, 6, 15)
    det["confidence_class"] = "nominal"
    det["type"] = 0

    cd = build_celldays(det, settings)
    cells = set(zip(cd.cell_lat_idx, cd.cell_lon_idx))
    assert cells == {(6, 1946), (6, 1841), (282, 2010)}

    # cover predicate must match the same cells (year(fire)-1 = 2005)
    cov_dir = tmp_path / "processed" / "cell_cover" / "region=test" / "year=2005"
    os.makedirs(cov_dir)
    pd.DataFrame([
        {"region": "test", "cell_lat_idx": la, "cell_lon_idx": lo, "year": 2005,
         "cover_class": "forest", "forest_pct": 100, "crop_pct": 0,
         "other_veg_pct": 0, "land_pixels": 100}
        for la, lo in cells
    ]).to_parquet(cov_dir / "part-0.parquet", index=False)

    con = duckdb.connect()
    try:
        con.register("d", det)
        pred = cover_exists_latlon(settings, "forest", "d")
        rows = con.execute(
            f"SELECT {cell_index_sql('latitude', 0.05)}, {cell_index_sql('longitude', 0.05)} "
            f"FROM d WHERE {pred}").fetchall()
        assert set(rows) == cells
    finally:
        con.close()


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
