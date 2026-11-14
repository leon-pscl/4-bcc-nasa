"""C9: build cell_cover from MCD12Q1 500 m GeoTIFF granules (WGS84) + QC layer.

Source: NASA AppEEARS, MCD12Q1.061, LC_Type1 (IGBP) layer, geographic WGS84,
500 m, yearly granules 2002..2024, cropped to the southeast_asia bbox. The 23
.tif files plus matching QC files live in data/raw/landcover/.

Per cell (0.05 deg, our grid) we aggregate the ~144 500 m pixels inside it:
IGBP class 1-5 = forest, 12/14 = farmland, 6-11 = other_vegetation,
13/15/16 = other; 17 water and 255 fill excluded. Only pixels with QC == 0
(confidently-classified land) are counted. Percentages are shares of *land*
pixels; cover_class is the majority group. Water-only cells carry no row.
"""

import glob
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np

IGBP_FOREST = {1, 2, 3, 4, 5}
IGBP_FARMLAND = {12, 14}
IGBP_OTHER_VEGETATION = {6, 7, 8, 9, 10, 11}
IGBP_OTHER = {13, 15, 16}
IGBP_LAND = IGBP_FOREST | IGBP_FARMLAND | IGBP_OTHER_VEGETATION | IGBP_OTHER
QC_KEEP = 0  # only confidently-classified land pixels contribute


def igbp_class_of(v):
    if v in IGBP_FOREST:
        return "forest"
    if v in IGBP_FARMLAND:
        return "farmland"
    if v in IGBP_OTHER_VEGETATION:
        return "other_vegetation"
    if v in IGBP_OTHER:
        return "other"
    return None  # water/fill: not a land class


def _region_bboxes(settings):
    """List of (name, (w,s,e,n)) for all loaded regions (config/regions.json)."""
    import json
    path = os.path.join("config", "regions.json")
    bboxes = []
    if os.path.exists(path):
        try:
            for r in json.load(open(path)).get("regions", []):
                bboxes.append((r["name"], tuple(float(x) for x in r["bbox"])))
        except Exception:
            pass
    for name, bbox in (getattr(settings, "REGIONS", {}) or {}).items():
        bboxes.append((name, tuple(bbox)))
    return bboxes


def _cell_table(bboxes):
    """int arrays (cell_lat_idx, cell_lon_idx, region_idx) for every loaded cell."""
    lats, lons, regs = [], [], []
    for ri, (_, (w, s, e, n)) in enumerate(bboxes):
        lat_lo = math.floor(s / 0.05)
        lat_hi = math.floor((n - 1e-12) / 0.05)
        lon_lo = math.floor(w / 0.05)
        lon_hi = math.floor((e - 1e-12) / 0.05)
        for la in range(lat_lo, lat_hi + 1):
            for lo in range(lon_lo, lon_hi + 1):
                lats.append(la)
                lons.append(lo)
                regs.append(ri)
    key = np.array(lats, dtype=np.int64) * 100000 + np.array(lons, dtype=np.int64)
    order = np.argsort(key)
    return (np.array(lats, dtype=np.int32)[order],
            np.array(lons, dtype=np.int32)[order],
            np.array(regs, dtype=np.int16)[order],
            key[order])


def _granule_year(path):
    m = re.search(r"doy(\d{4})\d{3}", os.path.basename(path))
    if not m:
        raise ValueError(f"cannot read granule year from {path} (expected ...doy<year>001... in name)")
    return int(m.group(1))


def build_cell_cover(settings, files=None, dry_run=False):
    """Every .tif granule in data/raw/landcover -> cell_cover/region=/year= hive."""
    import duckdb
    import pandas as pd
    import rasterio

    if files is None:
        files = sorted(glob.glob(os.path.join(settings.DATA_RAW, "landcover",
                                              "MCD12Q1.061_LC_Type1_*.tif")))
    if not files:
        raise FileNotFoundError(f"no LC granules in {os.path.join(settings.DATA_RAW, 'landcover')}")

    bboxes = _region_bboxes(settings)
    if not bboxes:
        raise ValueError("no loaded regions configured; cell_cover is built for loaded regions only")

    cell_lat, cell_lon, cell_reg, cell_key = _cell_table(bboxes)
    names = [b[0] for b in bboxes]
    region_of = np.array(names, dtype=object)

    written = []
    root = os.path.join(settings.DATA_PROCESSED, "cell_cover")
    for path in files:
        year = _granule_year(path)
        qc_path = path.replace("LC_Type1", "QC")
        if not os.path.exists(qc_path):
            raise FileNotFoundError(f"missing QC granule for {path}")
        counts = _aggregate(path, qc_path, cell_lat, cell_lon, cell_reg, cell_key)
        df = _frame_for_file(counts, region_of, cell_lat, cell_lon, cell_reg, year)
        if df is None:
            print("skipped", path, "(no land pixels)")
            continue
        con = duckdb.connect()
        con.execute("PRAGMA threads=2")
        con.execute("PRAGMA memory_limit='4GB'")
        tmp_root = os.path.join(settings.DATA_PROCESSED, "_duckdb_tmp")
        os.makedirs(tmp_root, exist_ok=True)
        con.execute(f"PRAGMA temp_directory='{tmp_root.replace(os.sep, '/')}'")
        con.register("cov", df)
        sql = ("SELECT region, cell_lat_idx, cell_lon_idx, "
               "CAST(year AS SMALLINT) AS year, cover_class, "
               "CAST(forest_pct AS TINYINT) AS forest_pct, "
               "CAST(crop_pct AS TINYINT) AS crop_pct, "
               "CAST(other_veg_pct AS TINYINT) AS other_veg_pct, "
               "CAST(land_pixels AS INTEGER) AS land_pixels FROM cov")
        tmp = Path(tempfile.mkdtemp(prefix="_part_", dir=settings.DATA_PROCESSED))
        try:
            con.execute(f"COPY ({sql}) TO '{tmp.as_posix()}/staging.parquet' "
                        f"(FORMAT PARQUET, COMPRESSION ZSTD)")
            src_n, dst_n = con.execute(
                f"SELECT (SELECT COUNT(*) FROM ({sql})), "
                f"(SELECT COUNT(*) FROM read_parquet('{tmp.as_posix()}/staging.parquet'))").fetchone()
            if src_n != dst_n:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError(f"cell_cover row mismatch: selected {src_n}, staged {dst_n} ({path})")
            if not dry_run:
                for reg in sorted(df["region"].unique()):
                    target = Path(root) / f"region={reg}" / f"year={year}"
                    if target.exists():
                        shutil.rmtree(target)
                    target.mkdir(parents=True)
                    con.execute(
                        f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}/staging.parquet') "
                        f"WHERE region = '{reg}') "
                        f"TO '{target.as_posix()}/part-{reg}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
            written.append((os.path.basename(path), year, int(len(df))))
            shutil.rmtree(tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        finally:
            con.close()
    return written


def _aggregate(lc_path, qc_path, cell_lat, cell_lon, cell_reg, cell_key):
    """Return per-cell (n_land, forest, farmland, other_veg, other) arrays for one granule."""
    import rasterio

    ncells = len(cell_key)
    n_land = np.zeros(ncells, dtype=np.int64)
    n_forest = np.zeros(ncells, dtype=np.int64)
    n_farm = np.zeros(ncells, dtype=np.int64)
    n_oveg = np.zeros(ncells, dtype=np.int64)
    n_other = np.zeros(ncells, dtype=np.int64)

    with rasterio.open(lc_path) as src:
        t = src.transform
        nrows, ncols = src.shape
        band = src.read(1)
        with rasterio.open(qc_path) as qc:
            qc_band = qc.read(1)
    keep = qc_band == QC_KEEP
    nrows, ncols = band.shape

    # map raster pixels to cell indices via the affine transform, block at a time
    lat_centers = t.f + (np.arange(nrows, dtype=np.float64) + 0.5) * t.e
    lon_centers = t.c + (np.arange(ncols, dtype=np.float64) + 0.5) * t.a
    lat_idx = np.floor(lat_centers / 0.05).astype(np.int64)
    lon_idx = np.floor(lon_centers / 0.05).astype(np.int64)
    # block-level key/search to bound temporary memory
    BLOCK = 256

    flat = band.ravel().astype(np.int32)
    keep_flat = keep.ravel()

    # precompute candidate search blocks (one row each, but search in bulk per block)
    for r0 in range(0, nrows, BLOCK):
        r1 = min(r0 + BLOCK, nrows)
        # build this block's keys in a 2D int64 array (~1.5 MB)
        block_keys = lat_idx[r0:r1, None] * 100000 + lon_idx[None, :]
        pos = np.searchsorted(cell_key, block_keys.ravel())
        pos = np.minimum(pos, len(cell_key) - 1)
        found = cell_key[pos] == block_keys.ravel()
        found = found.reshape(r1 - r0, ncols)
        pos = pos.reshape(r1 - r0, ncols).astype(np.int64)
        fl = flat[r0 * ncols:r1 * ncols].reshape(r1 - r0, ncols)
        kl = keep_flat[r0 * ncols:r1 * ncols].reshape(r1 - r0, ncols)
        if not found.any():
            continue
        m_land = kl & np.isin(fl, list(IGBP_LAND)) & found
        m_forest = kl & np.isin(fl, list(IGBP_FOREST)) & found
        m_farm = kl & np.isin(fl, list(IGBP_FARMLAND)) & found
        m_oveg = kl & np.isin(fl, list(IGBP_OTHER_VEGETATION)) & found
        m_other = kl & np.isin(fl, list(IGBP_OTHER)) & found
        if m_land.any():
            n_land += np.bincount(pos[m_land].ravel(), minlength=ncells)
            n_forest += np.bincount(pos[m_forest].ravel(), minlength=ncells)
            n_farm += np.bincount(pos[m_farm].ravel(), minlength=ncells)
            n_oveg += np.bincount(pos[m_oveg].ravel(), minlength=ncells)
            n_other += np.bincount(pos[m_other].ravel(), minlength=ncells)

    keep_mask = n_land > 0
    idx = np.nonzero(keep_mask)[0]
    n_land, n_forest, n_farm, n_oveg, n_other = (a[idx] for a in (n_land, n_forest, n_farm, n_oveg, n_other))
    return {
        "idx": idx,
        "n_land": n_land,
        "n_forest": n_forest,
        "n_farm": n_farm,
        "n_oveg": n_oveg,
        "n_other": n_other,
    }


def _frame_for_file(rows, region_of, cell_lat, cell_lon, cell_reg, year):
    import pandas as pd
    idx = rows["idx"]
    n_land = rows["n_land"].astype(np.int64)
    n_other = rows["n_other"].astype(np.int64)
    n_forest = rows["n_forest"].astype(np.int64)
    n_farm = rows["n_farm"].astype(np.int64)
    n_oveg = rows["n_oveg"].astype(np.int64)

    forest_pct = np.where(n_land > 0, n_forest * 100 / n_land, 0).astype(np.int64)
    crop_pct = np.where(n_land > 0, n_farm * 100 / n_land, 0).astype(np.int64)
    oveg_pct = np.where(n_land > 0, n_oveg * 100 / n_land, 0).astype(np.int64)

    stack = np.vstack([n_forest, n_farm, n_oveg, n_other]).astype(np.int64)
    cls = np.array(["forest", "farmland", "other_vegetation", "other"], dtype=object)[stack.argmax(axis=0)]

    return pd.DataFrame({
        "region": np.array([region_of[r] for r in cell_reg[idx]], dtype=object),
        "cell_lat_idx": cell_lat[idx],
        "cell_lon_idx": cell_lon[idx],
        "year": np.int16(year),
        "cover_class": cls,
        "forest_pct": forest_pct.astype(np.int8),
        "crop_pct": crop_pct.astype(np.int8),
        "other_veg_pct": oveg_pct.astype(np.int8),
        "land_pixels": n_land.astype(np.int32),
    })


def main():
    import argparse
    from firecal.config import Settings
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    written = build_cell_cover(settings, files=args.files, dry_run=args.dry_run)
    print("written:", written)


if __name__ == "__main__":
    main()
