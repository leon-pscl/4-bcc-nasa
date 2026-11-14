"""Audit MCD12Q1 cover_class stability: 2015-2020 baseline vs 2021-2024 (the
post-training-site-update window NASA flags as less reliable).

Reads data/processed/cell_cover/region=*/year=*/part*.parquet (build first with
python -m firecal.landcover.ingest) and reports:

  - cells whose majority cover_class changed in each consecutive year
    (2015->2016 ... 2023->2024), per region, with percentages of that region's
    mapped cells
  - aggregate mean year-to-year change in 2015-2020 vs 2021-2024

Usage: python scripts/audit_cover_shift.py
"""

import glob
import sys
from collections import Counter, defaultdict

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

con = duckdb.connect()
con.execute("PRAGMA threads=4")
con.execute("PRAGMA memory_limit='6GB'")

root = "data/processed/cell_cover/region=*/year=*/part*.parquet"
rows = con.execute(
    f"SELECT region, cell_lat_idx, cell_lon_idx, year, cover_class "
    f"FROM read_parquet('{root}')").fetchall()

per_cell = {}
counts_region = Counter()
for region, lat, lon, year, cls in rows:
    per_cell.setdefault((region, lat, lon), {})[year] = cls

total_cells_region = Counter()
for (region, _, _), years in per_cell.items():
    counts_region[region] += 1

def change(regos, y0, y1):
    changed = 0
    both = 0
    for (region, _, _), years in per_cell.items():
        if region not in regos:
            continue
        if y0 in years and y1 in years:
            both += 1
            if years[y0] != years[y1]:
                changed += 1
    return changed, both

years_present = sorted({y for years in per_cell.values() for y in years})
print("years present:", years_present)
for region in sorted(counts_region):
    print(f"region {region}: {counts_region[region]} cells present")
print()
print(f"{'window':>14} {'changed':>8} {'of':>8} {'pct':>8}")
base_stats = []
post_stats = []
for y0, y1 in zip(range(2015, 2025), range(2016, 2025)):
    changed, both = change(counts_region, y0, y1)
    pct = 100 * changed / both if both else 0
    print(f"{y0}->{y1:>4}{changed:>11}{both:>12}{pct:>7.2f}%")
    if y1 <= 2020:
        base_stats.append((changed, both))
    else:
        post_stats.append((changed, both))

def stats(lst):
    if not lst:
        return 0, 0
    t_changed = sum(c for c, _ in lst)
    t_both = sum(b for _, b in lst)
    return t_changed, t_both

c_b, b_b = stats(base_stats)
c_p, b_p = stats(post_stats)
print()
print(f"2015-2020: {c_b} changed of {b_b} = {100*c_b/b_b:.2f}%" if b_b else "2015-2020: n/a")
print(f"2021-2024: {c_p} changed of {b_p} = {100*c_p/b_p:.2f}%" if b_p else "2021-2024: n/a")
