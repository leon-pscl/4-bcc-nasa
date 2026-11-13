"""Map cells analytics (Stage 4): grid cells for the map, coarse when too many."""

from firecal.dataset import read_dataset

MAX_MAP_CELLS = 20_000


def map_cells(area, start, end, settings, month=None, region=None):
    import duckdb
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    root = read_dataset(settings, "harmonized_daily", [region] if region else None)
    cell_filter = area.bbox_sql(area)
    month_filter = f"AND EXTRACT(month FROM date_local) = {int(month)}" if month else ""
    where = f"""
        date_local >= DATE '{start}' AND date_local <= DATE '{end}'
          AND ({cell_filter}) {month_filter}
    """
    n = con.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM {root} WHERE {where}
            GROUP BY cell_lat_idx, cell_lon_idx
        )
    """).fetchone()[0]
    if n > MAX_MAP_CELLS:
        grid = 0.25
        aggregated_to = 5
        bin_lat, bin_lon = "FLOOR(cell_lat_idx / 5)", "FLOOR(cell_lon_idx / 5)"
    else:
        grid = 0.05
        aggregated_to = None
        bin_lat, bin_lon = "cell_lat_idx", "cell_lon_idx"
    rows = con.execute(f"""
        SELECT ROUND({bin_lat} * {grid} + {grid} / 2, 4) AS lat,
               ROUND({bin_lon} * {grid} + {grid} / 2, 4) AS lon,
               SUM(value) AS v
        FROM {root}
        WHERE {where}
        GROUP BY 1,2
    """).fetchall()
    return {"grid_deg": grid,
            "aggregated_to": aggregated_to,
            "cells": [{"lat": r[0], "lon": r[1], "value": r[2]} for r in rows]}
