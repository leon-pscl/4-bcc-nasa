"""C11 grid_cells: the 0.15 deg mask grid (86,328 cells for southeast_asia).

Per 15 km cell: geometry (center, fine_cells, area_km2), pixel-weighted
surface percentages from C10, forest/crop percentages from C9 (latest map,
display only), keep flag and mask_reason. Wetlands stay burnable (they are
in IGBP 1-14). The mask comes only from land cover, never from fire data.
A cell is kept iff burnable_pct (the pixel-weighted max over years) >= MASK_MIN_BURNABLE_PCT.
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from firecal.outlook import grid


def build_grid_cells(settings, region, dry_run=False):
    import duckdb

    bbox = settings.REGIONS.get(region)
    if bbox is None:
        raise ValueError(f"unknown region {region}")
    w, s, e, n = bbox

    surface_path = Path(settings.DATA_PROCESSED) / "cell_surface" / f"region={region}" / "part-0.parquet"
    if not surface_path.exists():
        raise FileNotFoundError(f"C10 not built yet: {surface_path} (run build-grid first)")
    con = duckdb.connect()
    src = f"read_parquet('{surface_path.as_posix()}')"

    g_lat_sql = grid.g_lat_sql("s")
    g_lon_sql = grid.g_lon_sql("s")
    rows = con.execute(f"""
        SELECT {g_lat_sql} AS g_lat_idx, {g_lon_sql} AS g_lon_idx,
               COUNT(*) AS fine_cells,
               SUM(total_px)::BIGINT AS px,
               SUM(water_pct * total_px) / NULLIF(SUM(total_px), 0) AS water_pct,
               SUM(barren_pct * total_px) / NULLIF(SUM(total_px), 0) AS barren_pct,
               SUM(snow_ice_pct * total_px) / NULLIF(SUM(total_px), 0) AS snow_ice_pct,
               SUM(burnable_pct_max * total_px) / NULLIF(SUM(total_px), 0) AS burnable_pct
        FROM {src} s
        GROUP BY 1, 2
        ORDER BY 1, 2
    """).fetchall()
    con.close()

    # geometry from the fine-cell universe of the box
    from firecal.outlook.surface import fine_cells_for_bbox
    fine_lat, fine_lon = fine_cells_for_bbox(bbox)
    fine_set = set(zip(fine_lat.tolist(), fine_lon.tolist()))

    cover_path = Path(settings.DATA_PROCESSED) / "cell_cover"
    forest_crop = {}
    if cover_path.exists():
        con = duckdb.connect()
        latest = con.execute(
            f"SELECT MAX(year) FROM read_parquet('{cover_path.as_posix()}/**/*.parquet')").fetchone()[0]
        if latest:
            for la, lo, fp, cp in con.execute(f"""
                SELECT cell_lat_idx, cell_lon_idx, forest_pct, crop_pct
                FROM read_parquet('{cover_path.as_posix()}/**/*.parquet')
                WHERE year = {latest}
            """).fetchall():
                forest_crop[(la, lo)] = (fp, cp)
        con.close()

    records = []
    for g_la, g_lo, fc, px, water, barren, snow, burn in rows:
        g_la, g_lo, fc, px = int(g_la), int(g_lo), int(fc), int(px)
        f_la0, f_la1 = grid.fine_range(g_la)
        f_lo0, f_lo1 = grid.fine_range(g_lo)
        cell_fine = [(la, lo) for la in range(f_la0, f_la1 + 1)
                     for lo in range(f_lo0, f_lo1 + 1)
                     if (la, lo) in fine_set]
        area = grid.cell_area_km2(g_la, g_lo, set(cell_fine))
        f_pct = c_pct = None
        if forest_crop:
            fws = [(forest_crop[p][0], 1) for p in cell_fine if p in forest_crop]
            cws = [(forest_crop[p][1], 1) for p in cell_fine if p in forest_crop]
            if fws:
                f_pct = sum(v for v, _ in fws) / len(fws)
            if cws:
                c_pct = sum(v for v, _ in cws) / len(cws)
        keep = burn >= settings.MASK_MIN_BURNABLE_PCT
        if keep:
            reason = "kept"
        else:
            # largest non-burnable share decides the reason
            reason = max((("water", water), ("barren", barren), ("snow_ice", snow)),
                         key=lambda kv: kv[1])[0]
        records.append({
            "region": region,
            "g_lat_idx": np.int32(g_la),
            "g_lon_idx": np.int32(g_lo),
            "center_lat": round(grid.g_center(g_la), 4),
            "center_lon": round(grid.g_center(g_lo), 4),
            "fine_cells": np.int8(fc),
            "area_km2": round(area, 3),
            "water_pct": water or 0.0,
            "barren_pct": barren or 0.0,
            "snow_ice_pct": snow or 0.0,
            "burnable_pct": burn or 0.0,
            "forest_pct": f_pct,
            "crop_pct": c_pct,
            "keep": bool(keep),
            "mask_reason": reason,
        })
    df = pd.DataFrame.from_records(records)
    if dry_run:
        return df
    from firecal.contracts import validate_grid_cells
    validate_grid_cells(df)

    root = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}"
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".part_", dir=str(root.parent))) / "part-0.parquet"
    df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
    validate_grid_cells(pd.read_parquet(tmp))
    os.replace(tmp, root / "part-0.parquet")
    tmp.parent.rmdir()
    return df
