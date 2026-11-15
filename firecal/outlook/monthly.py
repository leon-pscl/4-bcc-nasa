"""C12 monthly_cells: value per kept 15 km cell and month (value > 0 only).

value is the exact sum of the fine cells' harmonized values (C4), so the
calibration carries over. The cover split uses C9 with the usual year rule
(cover year = min(year(fire) - 1, latest map year)); value_forest + value_farmland
+ value_other may add up to less than value (fine cells with no C9 row).
Only years whose C4 fingerprint changed are rebuilt; monthly_cells.meta.json
records fingerprints, latest_date, partial_month and per-year totals.
"""

import json
import os
import tempfile
import time
from pathlib import Path

from firecal.dataset import (HARMONIZED, CELLDAYS, read_dataset, load_state,
                             write_partition, fingerprint, partition_key)

COVER_YEAR_MAX = None


def _cover_max_year(settings):
    global COVER_YEAR_MAX
    if COVER_YEAR_MAX:
        return COVER_YEAR_MAX
    import duckdb
    root = os.path.join(settings.DATA_PROCESSED, "cell_cover")
    if not os.path.isdir(root):
        return None
    con = duckdb.connect()
    try:
        row = con.execute(f"SELECT MAX(year) FROM read_parquet('{root.replace(os.sep, '/')}/**/*.parquet')").fetchone()
        COVER_YEAR_MAX = int(row[0]) if row and row[0] is not None else None
    finally:
        con.close()
    return COVER_YEAR_MAX


def _latest_date(settings, region):
    import duckdb
    root = os.path.join(settings.DATA_PROCESSED, HARMONIZED)
    con = duckdb.connect()
    try:
        row = con.execute(
            f"SELECT MAX(date_local) FROM read_parquet('{root.replace(os.sep, '/')}/region={region}/**/*.parquet')"
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        con.close()


def _partial_month(latest_date):
    """{year, month, through_day} when latest_date is not a month's last day, else None."""
    import calendar
    from datetime import date
    y, m, d = (int(p) for p in latest_date.split("-"))
    if d == calendar.monthrange(y, m)[1]:
        return None
    return {"year": y, "month": m, "through_day": d}


def build_monthly(settings, region, years=None, dry_run=False):
    import duckdb

    grid_path = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    if not grid_path.exists():
        raise FileNotFoundError(f"C11 not built yet: {grid_path} (run build-grid first)")

    state = load_state(settings)
    h_state = state.setdefault(HARMONIZED, {})
    grid_fp = state.get("grid_cells", {}).get(region, {}).get("fingerprint")
    m_state = state.setdefault("monthly_cells", {})
    meta_path = Path(settings.DATA_PROCESSED) / "monthly_cells.meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}

    h_root = os.path.join(settings.DATA_PROCESSED, HARMONIZED).replace(os.sep, "/")
    cov_root = os.path.join(settings.DATA_PROCESSED, "cell_cover").replace(os.sep, "/")
    g_src = f"read_parquet('{grid_path.as_posix()}')"
    cov_max = _cover_max_year(settings)

    available = sorted({int(k.split("/")[1]) for k in h_state if k.startswith(f"{region}/")})
    if years:
        available = [y for y in available if y in set(years)]
    target = []
    for y in available:
        fp = h_state.get(partition_key(region, y), {}).get("fingerprint")
        if fp and meta.get("years", {}).get(str(y), {}).get("fingerprint") == fp:
            m_state[partition_key(region, y)] = {"fingerprint": fingerprint(fp, grid_fp, y)}
            continue  # C4 unchanged: keep existing partition
        target.append(y)
    print(f"monthly_cells: rebuilding years {target or 'none (all up to date)'}")

    con = duckdb.connect()
    totals = {}
    try:
        for y in target:
            cover_year = min(y - 1, cov_max) if cov_max else None
            cover_join = ""
            if cover_year:
                cover_join = f"""
                LEFT JOIN read_parquet('{cov_root}/**/*.parquet') cov
                  ON cov.cell_lat_idx = h.cell_lat_idx AND cov.cell_lon_idx = h.cell_lon_idx
                 AND cov.year = {cover_year}
                """
            else:
                cover_join = "LEFT JOIN (SELECT NULL::VARCHAR AS cover_class, NULL::INTEGER AS cell_lat_idx, NULL::INTEGER AS cell_lon_idx WHERE FALSE) cov ON FALSE"
            sql = f"""
            WITH h AS (
              SELECT cell_lat_idx, cell_lon_idx, date_local, value
              FROM read_parquet('{h_root}/region={region}/year={y}/*.parquet')
            )
            SELECT '{region}' AS region, {y} AS year,
                   EXTRACT(month FROM h.date_local)::TINYINT AS month,
                   CAST(FLOOR(h.cell_lat_idx / 3.0) AS INTEGER) AS g_lat_idx,
                   CAST(FLOOR(h.cell_lon_idx / 3.0) AS INTEGER) AS g_lon_idx,
                   SUM(h.value) AS value,
                   COALESCE(SUM(h.value) FILTER (WHERE cov.cover_class = 'forest'), 0) AS value_forest,
                   COALESCE(SUM(h.value) FILTER (WHERE cov.cover_class = 'farmland'), 0) AS value_farmland,
                   COALESCE(SUM(h.value) FILTER (WHERE cov.cover_class IN ('other_vegetation', 'other')), 0) AS value_other,
                   COUNT(*)::INTEGER AS fine_celldays
            FROM h
            JOIN {g_src} g
              ON g.g_lat_idx = CAST(FLOOR(h.cell_lat_idx / 3.0) AS INTEGER)
             AND g.g_lon_idx = CAST(FLOOR(h.cell_lon_idx / 3.0) AS INTEGER)
             AND g.keep
            {cover_join}
            GROUP BY 3, 4, 5
            HAVING SUM(h.value) > 0
            """
            if not dry_run:
                write_partition(con, sql, settings, "monthly_cells", region, y)
            else:
                rows = con.execute(sql).fetchall()
                print(f"dry-run {y}: {len(rows)} rows")
            kept = con.execute(f"SELECT COALESCE(SUM(value), 0) FROM ({sql})").fetchone()[0]
            harmonized = con.execute(
                f"SELECT COALESCE(SUM(value), 0) FROM read_parquet('{h_root}/region={region}/year={y}/*.parquet')"
            ).fetchone()[0]
            totals[y] = {"fingerprint": h_state.get(partition_key(region, y), {}).get("fingerprint"),
                         "harmonized": harmonized, "kept": kept, "masked": harmonized - kept}
            m_state[partition_key(region, y)] = {
                "fingerprint": fingerprint(h_state.get(partition_key(region, y), {}).get("fingerprint"),
                                           grid_fp, y)}
            print(f"year {y}: harmonized {harmonized:.1f} kept {kept:.1f} masked {harmonized - kept:.1f} "
                  f"({(harmonized - kept) / harmonized * 100 if harmonized else 0:.3f}%)")
    finally:
        con.close()

    latest = _latest_date(settings, region)
    if not dry_run:
        from firecal.dataset import save_state
        save_state(settings, state)
    meta_years = meta.get("years", {})
    meta_years.update({str(y): t for y, t in totals.items()})
    meta = {
        "grid_deg": settings.OUTLOOK_GRID_DEG,
        "fine_per_g": 3,
        "mask": {"nonburnable_classes": list(settings.MASK_NONBURNABLE_CLASSES),
                 "min_burnable_pct": settings.MASK_MIN_BURNABLE_PCT},
        "threshold": settings.OUTLOOK_FIRE_THRESHOLD,
        "p_fire_rule": f"VIIRS years only (complete years >= {settings.OUTLOOK_PFIRE_START}); "
                       f"means/medians/expected from the full record 2003 on",
        "latest_date": latest,
        "partial_month": _partial_month(latest) if latest else None,
        "years": meta_years,
    }
    if not dry_run:
        tmp = str(meta_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
        os.replace(tmp, meta_path)
    return meta
