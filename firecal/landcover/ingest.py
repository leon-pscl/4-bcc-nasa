"""C9: build cell_cover from MCD12C1 HDF4 granules.

Source: MODIS land cover CMG, MCD12C1 v061, 0.05 deg, yearly, granule years
2002..2024 (plus 2024 used for fires in 2025+; see contract C9 and D21).

Each HDF4 granule holds global 3600x3600 grids (cell centers lat 89.975..-89.975,
lon -179.975..179.975, 0.05 deg). IGBP Type 1 mapped:

  IGBP 1-5   -> forest
  IGBP 12,14 -> farmland
  IGBP 6-11  -> other_vegetation
  everything else (13,15,16,17,255) -> other

`forest_pct` / `crop_pct` sum the Land_Cover_Type_1_Percent bands of the cell's
17 IGBP classes; `majority_confidence` is the Majority_Land_Cover_Type_1_Assessment
value as-is (0..100; fill 255 -> 0).

Rows are emitted only for cells that fall inside a loaded region's bbox (the
region list in config/regions.json). Partitioning is by year (Hive).
"""

import glob
import math
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

IGBP_FOREST = {1, 2, 3, 4, 5}
IGBP_FARMLAND = {12, 14}
IGBP_OTHER_VEGETATION = {6, 7, 8, 9, 10, 11}

FOREST_BANDS = [i - 1 for i in sorted(IGBP_FOREST)]
CROP_BANDS = [i - 1 for i in sorted(IGBP_FARMLAND)]

YEAR_COVER_MIN = 2002
YEAR_COVER_MAX = 2024


def igbp_class_of(v):
    if v in IGBP_FOREST:
        return "forest"
    if v in IGBP_FARMLAND:
        return "farmland"
    if v in IGBP_OTHER_VEGETATION:
        return "other_vegetation"
    return "other"


def _pct_band(pct, band):
    if pct.ndim == 3 and pct.shape[0] == 17:
        return pct[band]
    if pct.ndim == 3 and pct.shape[2] == 17:
        return pct[:, :, band]
    raise ValueError(f"Land_Cover_Type_1_Percent shape {pct.shape}, expected (17,3600,3600) or (3600,3600,17)")


def _region_bboxes(settings):
    """Ordered list of loaded region bboxes [(w,s,e,n)] from config/regions.json."""
    import json
    path = os.path.join("config", "regions.json")
    bboxes = []
    if os.path.exists(path):
        try:
            for r in json.load(open(path)).get("regions", []):
                w, s, e, n = r["bbox"]
                bboxes.append((float(w), float(s), float(e), float(n)))
        except Exception:
            pass
    regions = getattr(settings, "REGIONS", {}) or {}
    for _, bbox in regions.items():
        bboxes.append(tuple(bbox))
    return bboxes


def region_mask(bboxes):
    """Boolean mask of the global 3600x3600 grid for cells inside any bbox."""
    m = np.zeros((3600, 3600), dtype=bool)
    for w, s, e, n in bboxes:
        lat_lo_idx, lat_hi_idx = math.floor(s / 0.05), math.floor((n - 1e-12) / 0.05)
        lon_lo_idx, lon_hi_idx = math.floor(w / 0.05), math.floor((e - 1e-12) / 0.05)
        row_from = 1799 - lat_hi_idx
        row_to = 1799 - lat_lo_idx + 1
        col_from = lon_lo_idx + 3600
        col_to = lon_hi_idx + 3600 + 1
        m[row_from:row_to, col_from:col_to] = True
    return m


def build_cell_cover(settings, files=None, dry_run=False):
    """Every granule in data/raw/landcover/*.hdf -> cell_cover/year=YYYY partitioned parquet."""
    import duckdb
    import pandas as pd

    if files is None:
        files = sorted(glob.glob(os.path.join(settings.DATA_RAW, "landcover", "MCD12C1.A*.hdf")))
    if not files:
        raise FileNotFoundError(f"no granules in {os.path.join(settings.DATA_RAW, 'landcover')} "
                                f"(expected MCD12C1.A<year>001.061.*.hdf)")

    bboxes = _region_bboxes(settings)
    if not bboxes:
        raise ValueError("no loaded regions configured; cell_cover is built for loaded regions only")
    mask = region_mask(bboxes)
    tmp_root = os.path.join(settings.DATA_PROCESSED, "_duckdb_tmp")
    os.makedirs(tmp_root, exist_ok=True)

    import re
    written = []
    for path in files:
        m = re.search(r"\.A(\d{4})(\d{3})\.", os.path.basename(path))
        if not m:
            raise ValueError(f"cannot read granule year from {path}")
        year = int(m.group(1))
        df = _read_granule(path, mask)
        con = duckdb.connect()
        con.execute("PRAGMA threads=2")
        con.execute("PRAGMA memory_limit='4GB'")
        con.register("cov", df)
        sql = (f"SELECT CAST(cell_lat_idx AS INTEGER) AS cell_lat_idx, "
               f"CAST(cell_lon_idx AS INTEGER) AS cell_lon_idx, "
               f"CAST(year AS SMALLINT) AS year, cover_class, "
               f"CAST(forest_pct AS TINYINT) AS forest_pct, "
               f"CAST(crop_pct AS TINYINT) AS crop_pct, "
               f"CAST(majority_confidence AS TINYINT) AS majority_confidence FROM cov WHERE year = {year}")

        root = os.path.join(settings.DATA_PROCESSED, "cell_cover")
        os.makedirs(settings.DATA_PROCESSED, exist_ok=True)
        os.makedirs(tmp_root, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="_part_", dir=settings.DATA_PROCESSED))
        try:
            con.execute(f"COPY ({sql}) TO '{tmp.as_posix()}/staging.parquet' "
                        f"(FORMAT PARQUET, COMPRESSION ZSTD)")
            src_n, dst_n = con.execute(
                f"SELECT (SELECT COUNT(*) FROM ({sql})), "
                f"(SELECT COUNT(*) FROM read_parquet('{tmp.as_posix()}/staging.parquet'))").fetchone()
            if src_n != dst_n:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError(f"cell_cover row mismatch: selected {src_n}, staged {dst_n} (year {year})")
            target = os.path.join(root, f"year={year}")
            if os.path.exists(target):
                shutil.rmtree(target)
            if dry_run:
                shutil.rmtree(tmp)
            else:
                os.makedirs(root, exist_ok=True)
                if os.path.exists(target):
                    shutil.rmtree(target)
                os.makedirs(target)
                for f_ in tmp.rglob("*.parquet"):
                    os.replace(f_, os.path.join(target, f_.name))
                shutil.rmtree(tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        con.close()
        written.append(year)
    return written


def _read_granule(path, mask):
    import pandas as pd
    import re
    from pyhdf.SD import SD

    f = SD(path)
    try:
        ds_major = f.select("Majority_Land_Cover_Type_1")
        ds_asg = f.select("Majority_Land_Cover_Type_1_Assessment")
        ds_pct = f.select("Land_Cover_Type_1_Percent")
        year_en = int(re.search(r"\.A(\d{4})", os.path.basename(path)).group(1))
        majority = ds_major[:]
        majority = np.asarray(majority)
        assessment = np.asarray(ds_asg[:])
        pct = np.asarray(ds_pct[:])
    finally:
        f.end()

    forest_sum = np.zeros(majority.shape, dtype=np.int16)
    crop_sum = np.zeros(majority.shape, dtype=np.int16)
    for b in FOREST_BANDS:
        forest_sum += _pct_band(pct, b).astype(np.int16)
    for b in CROP_BANDS:
        crop_sum += _pct_band(pct, b).astype(np.int16)
    forest_pct = np.clip(forest_sum, 0, 100)
    crop_pct = np.clip(crop_sum, 0, 100)

    sel_major = majority[mask]
    sel_asg = assessment[mask]
    sel_forest = forest_pct[mask]
    sel_crop = crop_pct[mask]
    ys, xs = np.nonzero(mask)
    lat_ids = (1799 - ys).astype(np.int32)
    lon_ids = (xs - 3600).astype(np.int32)
    return pd.DataFrame({
        "cell_lat_idx": lat_ids.astype("int32"),
        "cell_lon_idx": lon_ids.astype("int32"),
        "year": np.int16(year_en),
        "cover_class": np.array([igbp_class_of(int(v)) for v in sel_major], dtype=object),
        "forest_pct": sel_forest.astype(np.int8),
        "crop_pct": sel_crop.astype(np.int8),
        "majority_confidence": np.where(sel_asg == 255, 0, sel_asg).astype(np.int8),
    })


def main():
    import argparse
    from firecal.config import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    years = build_cell_cover(settings, files=args.files, dry_run=args.dry_run)
    print("written cover years:", years)


if __name__ == "__main__":
    main()
