"""Query helpers for the outlook API (C6 additions).

Area semantics match the rest of the app: a 15 km cell is inside when its
center is (west/south inclusive, east/north exclusive); exact rational
comparison on the 0.15 deg grid. Kept cells only.
"""

import json
import os
from pathlib import Path

from firecal.outlook import grid as grid_mod


def outlook_version(settings):
    p = os.path.join(settings.DATA_PROCESSED, "data_version.json")
    try:
        with open(p) as f:
            dv = json.load(f)
        parts = [f"{dv.get(k, 'unknown')}" for k in ("monthly_cells", "outlook")]
        return "-".join(parts)
    except Exception:
        return "unknown"


_kept_cache = {}


def kept_cells(settings, region):
    """[(g_lat_idx, g_lon_idx, center_lat, center_lon)] of kept cells; cached per grid fingerprint."""
    from firecal.dataset import load_state
    fp = load_state(settings).get("grid_cells", {}).get(region, {}).get("fingerprint") or "unknown"
    key = (settings.DATA_PROCESSED, region, fp)
    hit = _kept_cache.get(key)
    if hit is not None:
        return hit
    import duckdb
    p = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT g_lat_idx, g_lon_idx, center_lat, center_lon FROM read_parquet('{p.as_posix()}') WHERE keep"
        ).fetchall()
    finally:
        con.close()
    cells = tuple((int(a), int(b), float(c), float(d)) for a, b, c, d in rows)
    if len(_kept_cache) > 4:
        _kept_cache.clear()
    _kept_cache[key] = cells
    return cells


def area_cells(settings, region, area):
    """Kept cells of the region inside the area (0.15 deg centers)."""
    out = []
    if area.radius_km is not None:
        from firecal.analytics.area import Area
        a15 = Area(lat=area.lat, lon=area.lon, radius_km=area.radius_km,
                   grid_deg=grid_mod.GRID_DEG)
        for la, lo, cla, clo in kept_cells(settings, region):
            if a15.cell_inside(la, lo):
                out.append((la, lo, cla, clo))
        return out
    for la, lo, cla, clo in kept_cells(settings, region):
        if grid_mod.cell_in_box(la, lo, area.w, area.s, area.e, area.n):
            out.append((la, lo, cla, clo))
    return out


def _temp_cells(con, cells):
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    con.execute("CREATE TEMP TABLE _outlook_cells (g_lat_idx INTEGER, g_lon_idx INTEGER)")
    if cells:
        con.executemany("INSERT INTO _outlook_cells VALUES (?, ?)", [(c[0], c[1]) for c in cells])


def _outlook_root(settings, region):
    return os.path.join(settings.DATA_PROCESSED, "outlook").replace(os.sep, "/") + f"/region={region}/**/*.parquet"


def _monthly_root(settings, region):
    return os.path.join(settings.DATA_PROCESSED, "monthly_cells").replace(os.sep, "/") + f"/region={region}/**/*.parquet"


def area_month_totals(con, settings, region, cells, first_year, last_year):
    """DataFrame: year, month, total value over the area's kept cells (baseline years only)."""
    monthly = _monthly_root(settings, region)
    _temp_cells(con, cells)
    rows = con.execute(f"""
        SELECT mc.year, mc.month, SUM(mc.value) AS total
        FROM read_parquet('{monthly}') mc
        JOIN _outlook_cells c ON c.g_lat_idx = mc.g_lat_idx AND c.g_lon_idx = mc.g_lon_idx
        WHERE mc.year BETWEEN {int(first_year)} AND {int(last_year)}
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    import pandas as pd
    df = pd.DataFrame(rows, columns=["year", "month", "total"])
    return df


def outlook_lead_totals(con, settings, region, cells, issued):
    """Per lead: (target_year, target_month, sum expected, cells with p_fire >= 0.5)."""
    outlook = _outlook_root(settings, region)
    _temp_cells(con, cells)
    rows = con.execute(f"""
        SELECT o.lead, o.target_year, o.target_month,
               SUM(o.expected), SUM(CASE WHEN o.p_fire >= 0.5 THEN 1 ELSE 0 END)
        FROM read_parquet('{outlook}') o
        JOIN _outlook_cells c ON c.g_lat_idx = o.g_lat_idx AND c.g_lon_idx = o.g_lon_idx
        WHERE o.issued = '{issued}'
        GROUP BY 1, 2, 3 ORDER BY 1
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    return rows


def issued_targets(con, settings, region):
    """(issued, [(lead, target_year, target_month)]) of the latest issue; targets are the 3 leads."""
    outlook = _outlook_root(settings, region)
    root = Path(settings.DATA_PROCESSED) / "outlook" / f"region={region}"
    if not root.exists() or not list(root.rglob("*.parquet")):
        return None, []
    row = con.execute(f"SELECT MAX(issued) FROM read_parquet('{outlook}')").fetchone()
    issued = row[0] if row else None
    if not issued:
        return None, []
    rows = con.execute(f"""
        SELECT DISTINCT lead, target_year, target_month FROM read_parquet('{outlook}')
        WHERE issued = '{issued}' ORDER BY lead
    """).fetchall()
    return issued, [(int(a), int(b), int(c)) for a, b, c in rows]


def top_cells(con, settings, region, cells, issued, per_lead=10):
    outlook = _outlook_root(settings, region)
    _temp_cells(con, cells)
    rows = con.execute(f"""
        SELECT o.lead, o.g_lat_idx, o.g_lon_idx, o.p_fire, o.expected
        FROM read_parquet('{outlook}') o
        JOIN _outlook_cells c ON c.g_lat_idx = o.g_lat_idx AND c.g_lon_idx = o.g_lon_idx
        WHERE o.issued = '{issued}'
        ORDER BY o.lead, o.p_fire DESC, o.expected DESC
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    from firecal.outlook.grid import g_center
    out = {}
    for lead, la, lo, p, exp in rows:
        lst = out.setdefault(int(lead), [])
        if len(lst) >= per_lead:
            continue
        lst.append({"lat": round(g_center(la), 4), "lon": round(g_center(lo), 4),
                    "lead": int(lead), "p_fire": round(float(p), 2), "expected": round(float(exp), 1)})
    return [c for lead in sorted(out) for c in out[lead]]


def map_cells(con, settings, region, cells, issued, lead):
    outlook = _outlook_root(settings, region)
    _temp_cells(con, cells)
    rows = con.execute(f"""
        SELECT o.g_lat_idx, o.g_lon_idx, o.p_fire, o.expected, o.mean_clim
        FROM read_parquet('{outlook}') o
        JOIN _outlook_cells c ON c.g_lat_idx = o.g_lat_idx AND c.g_lon_idx = o.g_lon_idx
        WHERE o.issued = '{issued}' AND o.lead = {int(lead)}
        ORDER BY o.g_lat_idx, o.g_lon_idx
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    from firecal.outlook.grid import g_center
    return [{"lat": round(g_center(a), 3), "lon": round(g_center(b), 3),
             "p_fire": round(float(c), 2), "expected": round(float(d), 1),
             "mean_clim": round(float(e), 1)} for a, b, c, d, e in rows]


def cells_rows(con, settings, region, cells, start, end, cap=2_000_000):
    """C12 rows for the area and [start, end] (month granularity), with centres."""
    monthly = _monthly_root(settings, region)
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    _temp_cells(con, cells)
    n = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{monthly}') mc
        JOIN _outlook_cells c ON c.g_lat_idx = mc.g_lat_idx AND c.g_lon_idx = mc.g_lon_idx
        WHERE mc.year * 12 + mc.month BETWEEN {sy * 12 + sm} AND {ey * 12 + em}
    """).fetchone()[0]
    if n > cap:
        con.execute("DROP TABLE IF EXISTS _outlook_cells")
        raise ValueError(f"cells export exceeds the {cap} row cap")
    rows = con.execute(f"""
        SELECT mc.year, mc.month, mc.g_lat_idx, mc.g_lon_idx, mc.value,
               mc.value_forest, mc.value_farmland, mc.value_other, mc.fine_celldays
        FROM read_parquet('{monthly}') mc
        JOIN _outlook_cells c ON c.g_lat_idx = mc.g_lat_idx AND c.g_lon_idx = mc.g_lon_idx
        WHERE mc.year * 12 + mc.month BETWEEN {sy * 12 + sm} AND {ey * 12 + em}
        ORDER BY mc.year, mc.month, mc.g_lat_idx, mc.g_lon_idx
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    from firecal.outlook.grid import g_center
    return [(int(y), int(m), round(g_center(a), 4), round(g_center(b), 4), v, vf, vfa, vo, fc)
            for y, m, a, b, v, vf, vfa, vo, fc in rows]


def issued_csv_rows(con, settings, region, cells):
    """Latest issued outlook rows for the area's kept cells (lead, then grid order)."""
    outlook = _outlook_root(settings, region)
    row = con.execute(f"SELECT MAX(issued) FROM read_parquet('{outlook}')").fetchone()
    issued = row[0] if row else None
    if not issued:
        return []
    _temp_cells(con, cells)
    rows = con.execute(f"""
        SELECT o.issued, o.lead, o.target_year, o.target_month, o.g_lat_idx, o.g_lon_idx,
               o.p_fire, o.p_fire_clim, o.expected, o.mean_clim, o.model
        FROM read_parquet('{outlook}') o
        JOIN _outlook_cells c ON c.g_lat_idx = o.g_lat_idx AND c.g_lon_idx = o.g_lon_idx
        WHERE o.issued = '{issued}'
        ORDER BY o.lead, o.g_lat_idx, o.g_lon_idx
    """).fetchall()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    return rows


def mask_stats(settings, region):
    """Cells by mask reason and the masked share of fire (from C11 + C12 meta)."""
    import duckdb
    p = Path(settings.DATA_PROCESSED) / "grid_cells" / f"region={region}" / "part-0.parquet"
    meta_path = Path(settings.DATA_PROCESSED) / "monthly_cells.meta.json"
    out = {"cells": {}, "masked_share_of_fire_pct": None}
    if p.exists():
        con = duckdb.connect()
        try:
            for reason, n in con.execute(f"select mask_reason, count(*) from read_parquet('{p.as_posix()}') group by 1").fetchall():
                out["cells"][reason] = int(n)
        finally:
            con.close()
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        harm = sum(y.get("harmonized", 0.0) for y in meta.get("years", {}).values())
        masked = sum(y.get("masked", 0.0) for y in meta.get("years", {}).values())
        out["masked_share_of_fire_pct"] = round(100 * masked / harm, 4) if harm else None
    return out


def area_single_month_total(con, settings, region, cells, year, month):
    monthly = _monthly_root(settings, region)
    _temp_cells(con, cells)
    row = con.execute(f"""
        SELECT COALESCE(SUM(mc.value), 0) FROM read_parquet('{monthly}') mc
        JOIN _outlook_cells c ON c.g_lat_idx = mc.g_lat_idx AND c.g_lon_idx = mc.g_lon_idx
        WHERE mc.year = {int(year)} AND mc.month = {int(month)}
    """).fetchone()
    con.execute("DROP TABLE IF EXISTS _outlook_cells")
    return float(row[0] if row else 0.0)


def season_block(totals, months=(1, 12)):
    """totals: DataFrame(year, month, total). Returns per-month median/mean arrays + peaks."""
    import statistics
    med, mean = [], []
    for m in range(1, 13):
        vals = totals.loc[totals["month"] == m, "total"].tolist()
        med.append(round(float(statistics.median(vals)), 1) if vals else 0.0)
        mean.append(round(float(statistics.fmean(vals)), 1) if vals else 0.0)
    order = sorted(range(12), key=lambda i: med[i], reverse=True)
    return {"normal_median": med, "normal_mean": mean,
            "peak_month": order[0] + 1,
            "busiest_months": [i + 1 for i in order[:3]]}


def month_p25_p75(totals, month):
    vals = totals.loc[totals["month"] == month, "total"].tolist()
    if not vals:
        return None
    import statistics
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return [round(float(q[0]), 1), round(float(q[-1]), 1)]


def month_mean_median(totals, month):
    vals = totals.loc[totals["month"] == month, "total"].tolist()
    if not vals:
        return None, None
    import statistics
    return (round(float(statistics.fmean(vals)), 1), round(float(statistics.median(vals)), 1))


def skill_numbers(settings, region):
    p = Path(settings.DATA_PROCESSED) / "validation" / f"outlook_{region}.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    pooled = data.get("pooled") or {}
    return {"top10_capture_pct": pooled.get("top10_capture_pct"),
            "brier": pooled.get("brier"),
            "test_years": [min(data.get("test_years", [2015, 2025])), max(data.get("test_years", [2015, 2025]))],
            "big_years": {str(y): data.get("per_year", {}).get(str(y), {}).get("top10_capture_pct")
                          for y in (2015, 2019, 2023)}}
