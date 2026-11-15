"""C10 cell_surface: per 0.05 deg cell, pixel counts from the MCD12Q1 granules.

One pass over the 23 LC_Type1 GeoTIFFs (no QC filter: every pixel counts).
Burnable = IGBP 1-14; not burnable: 15 snow/ice, 16 barren, 17 water, 255 fill/nodata.
Percentages are shares of the cell's total pixels; full double precision (weights
for C11). Water/barren/snow_ice percentages come from the latest (2024) map;
burnable_pct_max is the highest share over 2002-2024 and burnable_year_max the
year it occurred.
"""

import glob
import json
import math
import os
import re
import tempfile
from pathlib import Path

import numpy as np

IGBP_BURNABLE = set(range(1, 15))  # 1-14
WATER = 17
BARREN = 16
SNOW_ICE = 15
FILL = 255


def _region_bboxes(settings):
    import json as _json
    path = os.path.join("config", "regions.json")
    bboxes = []
    if os.path.exists(path):
        try:
            for r in _json.load(open(path)).get("regions", []):
                bboxes.append((r["name"], tuple(float(x) for x in r["bbox"])))
        except Exception:
            pass
    for name, bbox in (getattr(settings, "REGIONS", {}) or {}).items():
        bboxes.append((name, tuple(bbox)))
    return bboxes


def fine_cells_for_bbox(bbox):
    """(lat_idx, lon_idx) arrays of every fine cell whose center is in the box."""
    w, s, e, n = bbox
    lat_lo = math.floor(s / 0.05)
    lat_hi = math.floor((n - 1e-12) / 0.05)
    lon_lo = math.floor(w / 0.05)
    lon_hi = math.floor((e - 1e-12) / 0.05)
    lats = np.arange(lat_lo, lat_hi + 1, dtype=np.int32)
    lons = np.arange(lon_lo, lon_hi + 1, dtype=np.int32)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    return la.ravel(), lo.ravel()


def _cell_key(cell_lat, cell_lon):
    return cell_lat.astype(np.int64) * 100000 + cell_lon.astype(np.int64)


def _granule_year(path):
    m = re.search(r"doy(\d{4})\d{3}", os.path.basename(path))
    if not m:
        raise ValueError(f"cannot read granule year from {path}")
    return int(m.group(1))


def count_pixels(path, cell_lat, cell_lon, cell_key):
    """Per-cell pixel counts for one granule: total, burnable, water, barren, snow_ice."""
    import rasterio

    ncells = len(cell_key)
    total = np.zeros(ncells, dtype=np.int64)
    burnable = np.zeros(ncells, dtype=np.int64)
    water = np.zeros(ncells, dtype=np.int64)
    barren = np.zeros(ncells, dtype=np.int64)
    snow = np.zeros(ncells, dtype=np.int64)

    with rasterio.open(path) as src:
        t = src.transform
        band = src.read(1)
    nrows, ncols = band.shape

    lat_centers = t.f + (np.arange(nrows, dtype=np.float64) + 0.5) * t.e
    lon_centers = t.c + (np.arange(ncols, dtype=np.float64) + 0.5) * t.a
    lat_idx = np.floor(lat_centers / 0.05).astype(np.int64)
    lon_idx = np.floor(lon_centers / 0.05).astype(np.int64)

    burnable_vals = np.isin(np.arange(256, dtype=np.uint8), list(IGBP_BURNABLE))
    flat = band.ravel().astype(np.int32)

    BLOCK = 256
    order = np.argsort(cell_key)
    sorted_key = cell_key[order]
    for r0 in range(0, nrows, BLOCK):
        r1 = min(r0 + BLOCK, nrows)
        block_keys = lat_idx[r0:r1, None] * 100000 + lon_idx[None, :]
        pos = np.searchsorted(sorted_key, block_keys.ravel())
        pos = np.minimum(pos, len(sorted_key) - 1)
        found = sorted_key[pos] == block_keys.ravel()
        found = found.reshape(r1 - r0, ncols)
        pos = order[pos].reshape(r1 - r0, ncols)
        fl = flat[r0 * ncols:r1 * ncols].reshape(r1 - r0, ncols)
        if not found.any():
            continue
        m_burn = found & burnable_vals[fl]
        if m_burn.any():
            burnable += np.bincount(pos[m_burn].ravel(), minlength=ncells)
        m_water = found & (fl == WATER)
        if m_water.any():
            water += np.bincount(pos[m_water].ravel(), minlength=ncells)
        m_barren = found & (fl == BARREN)
        if m_barren.any():
            barren += np.bincount(pos[m_barren].ravel(), minlength=ncells)
        m_snow = found & (fl == SNOW_ICE)
        if m_snow.any():
            snow += np.bincount(pos[m_snow].ravel(), minlength=ncells)
        total += np.bincount(pos[found].ravel(), minlength=ncells)
    return total, burnable, water, barren, snow


def build_cell_surface(settings, region, files=None, dry_run=False):
    import pandas as pd

    if files is None:
        files = sorted(glob.glob(os.path.join(settings.DATA_RAW, "landcover",
                                              "MCD12Q1.061_LC_Type1_*.tif")))
    if not files:
        raise FileNotFoundError(f"no LC granules in {os.path.join(settings.DATA_RAW, 'landcover')}")
    bbox = settings.REGIONS.get(region)
    if bbox is None:
        raise ValueError(f"unknown region {region}")

    cell_lat, cell_lon = fine_cells_for_bbox(bbox)
    cell_key = _cell_key(cell_lat, cell_lon)
    n = len(cell_key)
    burn_pct_max = np.zeros(n, dtype=np.float64)
    burn_year_max = np.zeros(n, dtype=np.int16)
    total_latest = np.zeros(n, dtype=np.int64)
    water_latest = np.zeros(n, dtype=np.int64)
    barren_latest = np.zeros(n, dtype=np.int64)
    snow_latest = np.zeros(n, dtype=np.int64)
    latest_year = -1

    for path in files:
        year = _granule_year(path)
        total, burnable, water, barren, snow = count_pixels(path, cell_lat, cell_lon, cell_key)
        pct = np.where(total > 0, burnable * 100.0 / np.maximum(total, 1), 0.0)
        better = pct > burn_pct_max
        burn_pct_max = np.where(better, pct, burn_pct_max)
        burn_year_max = np.where(better, np.int16(year), burn_year_max).astype(np.int16)
        if year > latest_year:
            latest_year = year
            total_latest, water_latest, barren_latest, snow_latest = total, water, barren, snow
        print(f"surface: {os.path.basename(path)} year={year} cells={n}")

    safe_total = np.maximum(total_latest, 1)
    df = pd.DataFrame({
        "region": np.array([region] * n, dtype=object),
        "cell_lat_idx": cell_lat,
        "cell_lon_idx": cell_lon,
        "total_px": total_latest.astype(np.int32),
        "water_pct": water_latest * 100.0 / safe_total,
        "barren_pct": barren_latest * 100.0 / safe_total,
        "snow_ice_pct": snow_latest * 100.0 / safe_total,
        "burnable_pct_max": burn_pct_max,
        "burnable_year_max": burn_year_max,
    })
    if dry_run:
        return df
    from firecal.contracts import validate_surface
    validate_surface(df)

    root = Path(settings.DATA_PROCESSED) / "cell_surface" / f"region={region}"
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".part_", dir=str(root.parent))) / "part-0.parquet"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
    df_check = pd.read_parquet(tmp)
    validate_surface(df_check)
    os.replace(tmp, root / "part-0.parquet")
    tmp.parent.rmdir()
    return df
