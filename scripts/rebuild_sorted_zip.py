"""Rebuild processed_data_v2.zip with sorted parquet partitions (item 6a)."""
import hashlib, json, os, shutil, zipfile, tempfile
from pathlib import Path
import duckdb

SRC = Path("E:/snapshots/cloud/processed_data_v2.zip")
OUT = Path("E:/snapshots/cloud/processed_data_v2_sorted.zip")
EXTRACT = Path("C:/Users/Leon/AppData/Local/Temp/opencode/sorted_data")
RG = 75000

if EXTRACT.exists():
    shutil.rmtree(EXTRACT)
EXTRACT.mkdir(parents=True)

with zipfile.ZipFile(SRC) as z:
    z.extractall(EXTRACT)

con = duckdb.connect()

def sort_parquet(path, order_cols):
    tmp = path.with_suffix(".tmp.parquet")
    con.execute(f"COPY (SELECT * FROM read_parquet('{path.as_posix()}') ORDER BY {order_cols}) TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {RG})")
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{tmp.as_posix()}')").fetchone()[0]
    os.replace(tmp, path)
    return n

# harmonized_daily, celldays, monthly_cells: sort by cell_lat_idx, cell_lon_idx, date_local (if cols exist)
for name in ("harmonized_daily", "celldays", "monthly_cells"):
    root = EXTRACT / name
    if not root.exists():
        continue
    for p in root.rglob("*.parquet"):
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p.as_posix()}')").fetchall()]
        order = []
        for c in ("cell_lat_idx","g_lat_idx"):
            if c in cols: order.append(c)
        for c in ("cell_lon_idx","g_lon_idx"):
            if c in cols: order.append(c)
        # date column
        datecol = None
        for c in ("date_local","acq_date","month"):
            if c in cols:
                datecol = c; break
        if datecol: order.append(datecol)
        if not order:
            print("skip (no sort cols):", p); continue
        n = sort_parquet(p, ", ".join(order))
        print(f"sorted {name}: {p} rows={n} order={order}")

# detections: sort by latitude, longitude, acq_datetime_utc
root = EXTRACT / "detections"
if root.exists():
    for p in root.rglob("*.parquet"):
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p.as_posix()}')").fetchall()]
        order = []
        for c in ("latitude","longitude"):
            if c in cols: order.append(c)
        for c in ("acq_datetime_utc","acq_datetime"):
            if c in cols: order.append(c); break
        if not order:
            print("skip detections:", p); continue
        n = sort_parquet(p, ", ".join(order))
        print(f"sorted detections: {p} rows={n}")

con.close()

# rebuild zip
if OUT.exists():
    OUT.unlink()
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for p in sorted(EXTRACT.rglob("*")):
        if p.is_file():
            arc = p.relative_to(EXTRACT).as_posix()
            zout.write(p, arc)
print("OUT:", OUT, OUT.stat().st_size)
# sha256
h = hashlib.sha256()
with open(OUT,"rb") as f:
    for chunk in iter(lambda: f.read(1<<20), b""):
        h.update(chunk)
print("SHA256:", h.hexdigest())