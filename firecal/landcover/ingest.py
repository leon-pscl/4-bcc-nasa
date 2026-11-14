"""C9: build cell_cover from MCD12Q1 500 m GeoTIFF granules (WGS84).

Source: MODIS land cover, MCD12Q1.061, LC_Type1 layer (IGBP), cropped to the
region bbox(es) by AppEEARS, geographic WGS84, yearly, granule years 2002..2024
(plus 2024 used for fires in 2025+; see contract C9 and D21).

Each cell (0.05 deg, our grid) is a bucket of ~100x100 500 m pixels. Per cell:

  IGBP 1-5   -> forest
  IGBP 12,14 -> farmland
  IGBP 6-11  -> other_vegetation
  IGBP 13,15,16 -> other
  17 (water) and 255 (fill) are excluded from the counts entirely

C9 row per (region, cell_lat_idx, cell_lon_idx, year): cover_class (majority
group), forest_pct / crop_pct / other_veg_pct (share of *land* pixels, percent),
land_pixels. Partitioning is region/year Hive-style.
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

YEAR_COVER_MIN = 2002
YEAR_COVER_MAX = 2024


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


def _year_from_name(name):
    for pat in (r"A(\d{4})\d{3}", r"-(\d{4})\d{2}\d{2}_", r"_(\d{4})_\d{3}_", r"_(\d{4})_", r"\.(\d{4})\b"):
        m = re.search(pat, name)
        if m:
            y = int(m.group(1))
            if 1990 <= y <= 2100:
                return y
    return None


def build_cell_cover(settings, files=None, dry_run=False, year_override=None):
    """Every granule in data/raw/landcover/*.tif/tiff -> cell_cover/region=/year= hive."""
    import duckdb
    import pandas as pd

    if files is None:
        files = sorted(glob.glob(os.path.join(settings.DATA_RAW, "landcover", "*.tif")) +
                       glob.glob(os.path.join(settings.DATA_RAW, "landcover", "*.tiff")))
    if not files:
        raise FileNotFoundError(f"no granules in {os.path.join(settings.DATA_RAW, 'landcover')} "
                                f"(expected MCD12Q1 .tif)")

    bboxes = _region_bboxes(settings)
    if not bboxes:
        raise ValueError("no loaded regions configured; cell_cover is built for loaded regions only")
    names = [b[0] for b in bboxes]

    cell_lat, cell_lon, cell_reg, cell_key = _cell_table(bboxes)
    root = os.path.join(settings.DATA_PROCESSED, "cell_cover")
    written = []
    for path in files:
        import rasterio
        with rasterio.open(path) as src:
            band = src.read(1)
            t = src.transform
            nrows, ncols = band.shape
        year = _year_from_name(os.path.basename(path)) or year_override
        if year is None:
            raise ValueError(f"cannot read granule year from {path}; rename to include the year "
                             f"or pass --year")

        rows = _aggregate(band, t, nrows, ncols, cell_lat, cell_lon, cell_reg, cell_key,
                          names, year)
        df = pd.DataFrame(rows)
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
            written.append((os.path.basename(path), year))
            shutil.rmtree(tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        finally:
            con.close()
    return written


def _claim_map(band, t, nrows, ncols, cell_key):
    """Raster cell -> index into cell_key, or -1."""
    out = np.full((nrows, ncols), -1, dtype=np.int32)
    # WGS84 geographic: pixel height negative (origin top), width positive
    lat_centers = t.f + (np.arange(nrows, dtype=np.float64) + 0.5) * t.e
    lon_centers = t.c + (np.arange(ncols, dtype=np.float64) + 0.5) * t.a
    lat_idx_all = np.floor(lat_centers / 0.05).astype(np.int64)
    lon_idx = np.floor(lon_centers / 0.05).astype(np.int64)
    keys_base = lon_idx.astype(np.int64)
    n_key = len(cell_key)
    for j in range(nrows):
        keys = lat_idx_all[j] * 100000 + keys_base
        pos = np.searchsorted(cell_key, keys)
        pos = np.minimum(pos, n_key - 1)
        found = cell_key[pos] == keys
        if found.any():
            row = out[j]
            row[found] = pos[found].astype(np.int32)
    return out


def _aggregate(band, t, nrows, ncols, cell_lat, cell_lon, cell_reg, cell_key,
               region_names, year):
    cell_map = _claim_map(band, t, nrows, ncols, cell_key)
    ncells = len(cell_key)
    flat = band.ravel().astype(np.int32)
    mflat = cell_map.ravel()

    def cnt(mask):
        m = mask & (mflat >= 0)
        return np.bincount(mflat[m], minlength=ncells)

    n_land = cnt(np.isin(flat, list(IGBP_LAND)))
    n_for = cnt(np.isin(flat, list(IGBP_FOREST)))
    n_farm = cnt(np.isin(flat, list(IGBP_FARMLAND)))
    n_oveg = cnt(np.isin(flat, list(IGBP_OTHER_VEGETATION)))
    n_other = np.maximum(n_land - n_for - n_farm - n_oveg, 0)

    keep = n_land > 0
    idx = np.nonzero(keep)[0]
    n_land, n_other, n_for, n_farm, n_oveg = (a[idx] for a in (n_land, n_other, n_for, n_farm, n_oveg))

    def pct_of(count):
        return np.where(n_land > 0, count * 100 / n_land, 0).astype(np.int64)

    forest_pct, crop_pct, oveg_pct = pct_of(n_for), pct_of(n_farm), pct_of(n_oveg)

    stack = np.vstack([n_for, n_farm, n_oveg, n_other]).astype(np.int64)
    cls = np.array(["forest", "farmland", "other_vegetation", "other"], dtype=object)[stack.argmax(axis=0)]

    return {
        "region": np.array([region_names[r] for r in cell_reg[idx]], dtype=object),
        "cell_lat_idx": cell_lat[idx],
        "cell_lon_idx": cell_lon[idx],
        "year": np.int16(year),
        "cover_class": cls,
        "forest_pct": forest_pct.astype(np.int8),
        "crop_pct": crop_pct.astype(np.int8),
        "other_veg_pct": oveg_pct.astype(np.int8),
        "land_pixels": n_land.astype(np.int32),
    }


def main():
    import argparse
    from firecal.config import Settings
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--year", type=int, default=None,
                        help="year for granules whose filename doesn't encode it")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    written = build_cell_cover(settings, files=args.files, dry_run=args.dry_run,
                               year_override=args.year)
    print("written:", written)


if __name__ == "__main__":
    main()
