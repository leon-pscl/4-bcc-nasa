"""Reality check: monthly totals for the starter areas + k per tile."""

import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import duckdb

AREAS = {
    "central_kalimantan": (110.7, -3.6, 115.9, 0.8),
    "northern_thailand": (97.3, 17.0, 101.5, 20.5),
    "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738),
    "rondonia": (-66.0, -13.7, -60.0, -7.9),
    "bolivia_east": (-64, -18, -60, -14),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harmonized", default="data/processed/harmonized_daily.parquet")
    ap.add_argument("--calibration", default="data/processed/calibration.parquet")
    ap.add_argument("--areas", nargs="*", default=list(AREAS))
    args = ap.parse_args()
    con = duckdb.connect()
    h = "read_parquet('" + args.harmonized + "')"
    for name in args.areas:
        w, s, e, n = AREAS[name]
        sql = f"""
        SELECT EXTRACT(year FROM date_local)::INTEGER AS y,
               EXTRACT(month FROM date_local)::INTEGER AS m,
               SUM(value) AS v
        FROM {h}
        WHERE cell_lat_idx * 0.05 + 0.025 BETWEEN {s} AND {n}
          AND cell_lon_idx * 0.05 + 0.025 BETWEEN {w} AND {e}
        GROUP BY 1,2 ORDER BY 1,2
        """
        rows = con.execute(sql).fetchall()
        by_year = {}
        for y, m, v in rows:
            by_year.setdefault(y, {})[m] = v
        print("=== " + name)
        for y in sorted(by_year):
            top = sorted(by_year[y].items(), key=lambda kv: -(kv[1] or 0))[:3]
            print(f"  {y}: top months {[(m, round(v)) for m, v in top]}")
        # peak month across all years
        tot = {}
        for y, d in by_year.items():
            for m, v in d.items():
                tot[m] = tot.get(m, 0) + (v or 0)
        print("  season (sum over years, top 4 months):",
              [(m, round(v)) for m, v in sorted(tot.items(), key=lambda kv: -kv[1])[:4]])
    print("=== k per tile (tile_month rows)")
    ks = con.execute("SELECT tile_id, k FROM read_parquet('" + args.calibration + "') WHERE level='tile_month'").fetchall()
    import statistics
    per_tile = {}
    for t, k in ks:
        per_tile.setdefault(t, []).append(k)
    vals = [k for t, ks_ in per_tile.items() for k in ks_]
    print("tiles:", len(per_tile))
    print("k median:", round(statistics.median(vals), 4), "min:", round(min(vals), 4), "max:", round(max(vals), 4))
    top = sorted(((statistics.median(v), t) for t, v in per_tile.items()), reverse=True)[:5]
    print("highest median tiles:", [(t, round(v, 3)) for v, t in top])
    bottom = sorted(((statistics.median(v), t) for t, v in per_tile.items()))[:5]
    print("lowest median tiles:", [(t, round(v, 3)) for v, t in bottom])

if __name__ == "__main__":
    main()
