"""DuckDB cell-day builder (C2).

Reads the detections dataset and writes Hive-partitioned cell-day partitions
(region, year). Only partitions whose inputs changed are rebuilt.
"""

import duckdb

from firecal.dataset import fingerprint, partition_key, read_dataset, write_partition


def build_celldays_sql(source_sql, grid_deg, tile_deg, confidence_keep, keep_types):
    conf = ", ".join("'" + c + "'" for c in confidence_keep)
    types = ", ".join(str(t) for t in keep_types)
    return f"""
    SELECT
        region,
        CAST(FLOOR(latitude / {grid_deg}) AS INTEGER)  AS cell_lat_idx,
        CAST(FLOOR(longitude / {grid_deg}) AS INTEGER) AS cell_lon_idx,
        CAST(FLOOR(latitude / {tile_deg}) AS VARCHAR) || '_' ||
             CAST(FLOOR(longitude / {tile_deg}) AS VARCHAR) AS tile_id,
        date_local,
        CAST(EXTRACT(year FROM date_local) AS INTEGER) AS year,
        platform,
        CAST(COUNT(*) AS INTEGER) AS n_detections,
        CAST(SUM(frp) AS DOUBLE)  AS frp_sum
    FROM {source_sql}
    WHERE confidence_class IN ({conf})
      AND (type IS NULL OR type IN ({types}))
    GROUP BY 1,2,3,4,5,6,7
    """


def rebuild(settings, region=None, force_years=None, state=None):
    """Rebuild the changed celldays partitions. Returns list of rebuilt keys."""
    from firecal.dataset import CELLDAYS, load_state, save_state

    state = state if state is not None else load_state(settings)
    ds_state = state.setdefault(CELLDAYS, {})
    det_state = state.get("detections", {})
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='4GB'")

    src = read_dataset(settings, "detections", [region] if region else None)
    rebuilt = []
    for key, meta in sorted(det_state.items()):
        r, y = key.split("/")
        if region and r != region:
            continue
        year = int(y)
        if force_years is not None and year not in force_years:
            continue
        part_fp = fingerprint(det_state[key].get("fingerprint"), settings.GRID_DEG,
                              settings.TILE_DEG, tuple(settings.CONFIDENCE_KEEP),
                              tuple(settings.KEEP_TYPES))
        if ds_state.get(key, {}).get("fingerprint") == part_fp:
            continue
        sql = build_celldays_sql(src, settings.GRID_DEG, settings.TILE_DEG,
                                 settings.CONFIDENCE_KEEP, settings.KEEP_TYPES)
        part_sql = f"SELECT * FROM ({sql}) WHERE year = {year}"
        write_partition(con, part_sql, settings, CELLDAYS, r, year)
        ds_state[key] = {"fingerprint": part_fp}
        rebuilt.append(key)
    save_state(settings, state)
    return rebuilt
