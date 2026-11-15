"""C14 outlook: the issued monthly outlook (climatology only tonight).

Issue month = the last complete month on or before latest_date. Targets are
the next OUTLOOK_LEADS months. p_fire/expected come straight from C13 (model
= "climatology"); p_fire_clim and mean_clim equal the same numbers tonight.
Each issue is added to its issue-year's partition; past outlooks stay.
"""

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd

from firecal.dataset import write_partition, partition_key


def issue_month(latest_date):
    """(issued YYYY-MM, [(target_year, target_month, lead), ...])."""
    d = date.fromisoformat(latest_date)
    # last complete month on or before latest_date: complete when latest_date is its last day
    import calendar
    if d.day == calendar.monthrange(d.year, d.month)[1]:
        iy, im = d.year, d.month
    else:
        iy, im = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    leads = []
    y, m = iy, im
    for lead in range(1, 4):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        leads.append((y, m, lead))
    return f"{iy:04d}-{im:02d}", leads


def build_outlook(settings, region, latest_date, dry_run=False):
    import duckdb
    from firecal.outlook.climatology import build_climatology

    climatology = build_climatology(settings, region, latest_date, dry_run=dry_run)
    issued, leads = issue_month(latest_date)
    print(f"outlook: issued {issued}, targets " +
          ", ".join(f"{y}-{m:02d} (lead {l})" for y, m, l in leads))

    con = duckdb.connect()
    clim_root = os.path.join(settings.DATA_PROCESSED, "climatology").replace(os.sep, "/")
    rows = []
    for y, m, lead in leads:
        rows.append(con.execute(f"""
            SELECT '{region}' AS region, '{issued}' AS issued, {lead}::TINYINT AS lead,
                   {y}::SMALLINT AS target_year, {m}::TINYINT AS target_month,
                   g_lat_idx, g_lon_idx, p_fire, mean AS expected,
                   p_fire AS p_fire_clim, mean AS mean_clim, 'climatology' AS model
            FROM read_parquet('{clim_root}/region={region}/part-0.parquet')
            WHERE month = {m}
        """).df())
    con.close()
    new = pd.concat(rows, ignore_index=True)

    # merge with any past issues of the same issue-year partition
    issues_path = Path(settings.DATA_PROCESSED) / "outlook" / f"region={region}" / f"year={issued[:4]}"
    existing = []
    if issues_path.exists():
        for f in issues_path.glob("*.parquet"):
            existing.append(pd.read_parquet(f))
    if existing:
        old = pd.concat(existing, ignore_index=True)
        new = pd.concat([old[old["issued"] != issued], new], ignore_index=True)

    if dry_run:
        print(f"dry-run outlook: {len(new)} rows")
        return new, issued, leads

    from firecal.contracts import validate_outlook
    validate_outlook(new)
    for col, t in (("g_lat_idx", "int32"), ("g_lon_idx", "int32"), ("lead", "int8"),
                   ("target_year", "int16"), ("target_month", "int8")):
        new[col] = new[col].astype(t)
    tmp_pq = str(Path(settings.DATA_PROCESSED) / f".outlook_new_{issued}.parquet")
    new.to_parquet(tmp_pq, engine="pyarrow", compression="zstd", index=False)
    con = duckdb.connect()
    try:
        tmp_pq_sql = tmp_pq.replace(os.sep, "/")
        write_partition(con,
                        f"SELECT *, CAST(split_part(issued, '-', 1) AS SMALLINT) AS year "
                        f"FROM read_parquet('{tmp_pq_sql}')", settings,
                        "outlook", region, int(issued[:4]))
    finally:
        con.close()
        os.unlink(tmp_pq)
    return new, issued, leads
