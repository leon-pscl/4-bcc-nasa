"""Stage 4 point+radius and area validation tests."""

import math
import os
from datetime import date

import pandas as pd
import pytest

from firecal.analytics.area import Area
from firecal.cells.grid import cell_range
from firecal.config import Settings


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def test_bolivia_east_area():
    from firecal.analytics.area import Area
    a = Area.from_bbox(-64, -18, -60, -14)
    assert abs(a.area_km2() - 190_127) < 100


def test_antimeridian_bbox_rejected():
    from firecal.analytics.area import Area
    with pytest.raises(ValueError):
        Area.from_bbox(170, -10, -170, 10)


def test_bbox_cell_on_boundary():
    from firecal.analytics.area import Area
    g = 0.05
    # grid 0.05: cell 5 center = 0.275 (lat and lon axes)
    # south edge inclusive: cell center exactly on s -> inside
    a = Area.from_bbox(0.0, 0.275, 1.0, 1.0)
    assert a.cell_inside(5, 1) is True
    # north edge exclusive: cell center exactly on n -> outside
    a2 = Area.from_bbox(0.0, 0.0, 1.0, 0.325)
    assert a2.cell_inside(6, 1) is False
    assert a2.cell_inside(5, 1) is True
    # west edge inclusive: cell center exactly on w -> inside
    a3 = Area.from_bbox(0.075, 0.0, 1.0, 1.0)
    assert a3.cell_inside(5, 1) is True
    # east edge exclusive: cell center exactly on e -> outside
    a4 = Area.from_bbox(0.0, 0.0, 0.075, 1.0)
    assert a4.cell_inside(5, 1) is False





def test_cell_range_known_values():
    assert cell_range(-11.0, -10.825, 0.05) == (-220, -218)
    assert cell_range(97.3, 101.5, 0.05) == (1946, 2029)


def test_box_edge_on_cell_center_negative():
    from firecal.analytics.area import Area
    # cell -217's center is -10.825: south edge inclusive, north edge exclusive
    a = Area.from_bbox(-100.0, -10.825, -99.0, 0.0)
    assert a.cell_inside(-217, -1990) is True
    a2 = Area.from_bbox(-100.0, -11.0, -99.0, -10.825)
    assert a2.cell_inside(-217, -1990) is False


def test_box_boxes_cell_inside_matches_bbox_sql():
    import duckdb
    from firecal.analytics.area import Area
    boxes = [
        (0.275, 0.275, 2.325, 2.325),     # positive edges on cell centers
        (-2.325, -2.325, -0.275, -0.275),  # negative edges on cell centers
        (-1.025, -0.525, 1.525, 0.775),    # mixed
    ]
    for w, s, e, n in boxes:
        a = Area.from_bbox(w, s, e, n)
        g = 0.05
        lat_lo = int(s / g) - 1
        lat_hi = int(n / g) + 1
        lon_lo = int(w / g) - 1
        lon_hi = int(e / g) + 1
        idx = [(la, lo) for la in range(lat_lo, lat_hi + 1) for lo in range(lon_lo, lon_hi + 1)]
        py_cells = {(la, lo) for la, lo in idx if a.cell_inside(la, lo)}
        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE cells(cell_lat_idx INTEGER, cell_lon_idx INTEGER)")
            con.executemany("INSERT INTO cells VALUES (?, ?)", idx)
            sql_cells = {(la, lo) for la, lo in con.execute(
                f"SELECT cell_lat_idx, cell_lon_idx FROM cells WHERE {a.bbox_sql(a)}").fetchall()}
        finally:
            con.close()
        assert py_cells == sql_cells, (w, s, e, n)


def test_point_radius_boundary_exact():
    from firecal.analytics.area import Area
    g = 0.05
    lat, lon = 0.025, 0.025          # center of cell (0, 0)
    d = _haversine_km(0, 0, lat, lon)  # distance from origin to that cell center
    a = Area.from_point(0.0, 0.0, d)
    assert a.cell_inside(0, 0) is True          # exactly on the radius
    a2 = Area.from_point(0.0, 0.0, d * 0.999999999)
    assert a2.cell_inside(0, 0) is False        # one nanometer inside: outside
    a3 = Area.from_point(0.0, 0.0, d * 1.000000001)
    assert a3.cell_inside(0, 0) is True         # one nanometer outside: inside (tolerance)


def _fixture(tmp_path):
    root = tmp_path / "data"
    os.makedirs(root / "processed" / "harmonized_daily", exist_ok=True)
    rows = [
        (0, 0, date(2003, 6, 1), 2.0),
        (0, 0, date(2004, 6, 1), 8.0),
        (0, 0, date(2005, 6, 1), 16.0),
        (2, 3, date(2005, 6, 2), 32.0),
        (2, 3, date(2005, 7, 2), 64.0),
    ]
    import pandas as pd
    df = pd.DataFrame(rows, columns=["cell_lat_idx", "cell_lon_idx", "date_local", "value"])
    df["tile_id"] = "0_0"
    df["basis"] = "viirs"
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df["region"] = "test_region"
    import duckdb
    con = duckdb.connect()
    p = str(root / "processed" / "harmonized_daily").replace(os.sep, "/")
    con.execute(f"""
        COPY (SELECT * FROM df)
        TO '{p}' (FORMAT PARQUET, PARTITION_BY (region, year))
    """)
    import json
    json.dump([{"name": "test_region", "label": "Test", "bbox": [-180, -90, 180, 90],
                "countries": ["Test"], "start": "2003-01-01", "end": "2005-07-02",
                "platforms": ["Aqua", "SNPP"], "latest_date": "2005-07-02",
                "synthetic": False}], open(root / "processed" / "coverage.json", "w"))
    settings = Settings()
    settings.DATA_PROCESSED = str(root / "processed")
    settings.GRID_DEG = 0.05
    settings.TILE_DEG = 1.0
    settings.MAX_AREA_KM2 = 500_000
    settings.MIN_BASELINE_YEARS = 1
    return settings


def test_point_radius_calendar_hand_worked(tmp_path):
    settings = _fixture(tmp_path)
    from firecal.analytics.area import Area
    from firecal.analytics.calendar import calendar_matrix
    import os
    # point radius that covers only cell (0, 0)
    d = _haversine_km(0, 0, 0.025, 0.025)
    a = Area.from_point(0.0, 0.0, d + 1e-3)
    result = calendar_matrix(a, "2003-01-01", "2005-07-02", "2005-07-02",
                             settings, region="test_region")
    assert result["values"][0][5] == 2.0
    assert result["values"][1][5] == 8.0
    assert result["values"][2][5] == 16.0
    assert result["values"][2][6] == 0.0  # in-range month with no cells in the radius counts as 0.0
