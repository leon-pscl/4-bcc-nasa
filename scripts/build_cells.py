"""Build C2 cell-days from detections parquet(s) with DuckDB (vectorized)."""

import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grid-deg", type=float, default=0.05)
    ap.add_argument("--tile-deg", type=float, default=1.0)
    ap.add_argument("--confidence-keep", nargs="+", default=["nominal", "high"])
    ap.add_argument("--keep-types", nargs="+", type=int, default=[0])
    args = ap.parse_args()

    files = ", ".join("'" + p + "'" for p in args.inputs)
    conf = ", ".join("'" + c + "'" for c in args.confidence_keep)
    types = ", ".join(str(t) for t in args.keep_types)

    sql = f"""
    SELECT
        CAST(FLOOR(latitude / {args.grid_deg}) AS INTEGER)  AS cell_lat_idx,
        CAST(FLOOR(longitude / {args.grid_deg}) AS INTEGER) AS cell_lon_idx,
        CAST(FLOOR(latitude / {args.tile_deg}) AS VARCHAR) || '_' ||
             CAST(FLOOR(longitude / {args.tile_deg}) AS VARCHAR) AS tile_id,
        date_local,
        platform,
        CAST(COUNT(*) AS INTEGER) AS n_detections,
        CAST(SUM(frp) AS DOUBLE)  AS frp_sum
    FROM read_parquet([{files}])
    WHERE confidence_class IN ({conf})
      AND (type IS NULL OR type IN ({types}))
    GROUP BY 1, 2, 3, 4, 5
    """
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")
    t0 = time.time()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    con.execute(f"COPY ({sql}) TO '{args.out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    print("cell-days:", n, "time:", time.time() - t0)


if __name__ == "__main__":
    main()
