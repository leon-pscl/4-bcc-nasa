"""Migrate C1 detections to the slim schema (drop the stored `uid` column).

uid was 32-char md5 hex text and accounted for ~0.784 GB (~47%) of the table.
It is derived data: ingest recomputes it inline for dedup and never stores it.

Dry-run by default. With --apply, each (region, year) partition is rewritten
through write_partition (staging + row-count check + atomic swap), so a failed
migration never touches the published data. Idempotent: partitions already
without uid are skipped.

Note: data_version.json fingerprints the *inputs* of each partition, not its
bytes, so it does NOT change after this migration. Restart the app / flush its
response cache after running it.

Usage:
  python scripts/migrate_c1_slim.py            # dry run, prints per-partition plan
  python scripts/migrate_c1_slim.py --apply    # rewrite the partitions
"""

import argparse
import sys

from firecal.duck import connect
from firecal.config import Settings
from firecal.dataset import DETECTIONS, dataset_dir, write_partition

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true", help="rewrite partitions (default: dry run)")
args = parser.parse_args()

settings = Settings.from_env()
con = connect(settings, "pipeline")
root = dataset_dir(settings, DETECTIONS)

total_before = total_after = total_rows = 0
migrated = skipped = 0
for region_dir in sorted(root.glob("region=*")):
    region = region_dir.name.split("=", 1)[1]
    for year_dir in sorted(region_dir.glob("year=*")):
        year = int(year_dir.name.split("=", 1)[1])
        files = [f for f in year_dir.glob("*.parquet")]
        if not files:
            continue
        glob = str(year_dir / "*.parquet").replace("\\", "/")
        cols = {r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()}
        rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{glob}')").fetchone()[0]
        before = sum(f.stat().st_size for f in files)
        total_rows += rows
        if "uid" not in cols:
            print(f"SKIP {region}/{year}: already slim ({rows} rows, {before/1e6:.1f} MB)")
            skipped += 1
            continue
        print(f"{'MIGRATE' if args.apply else 'PLAN'} {region}/{year}: "
              f"{rows} rows, {before/1e6:.1f} MB, drop uid")
        total_before += before
        if args.apply:
            write_partition(con, f"SELECT * EXCLUDE (uid) FROM read_parquet('{glob}')",
                            settings, DETECTIONS, region, year)
            after_files = list((root / f"region={region}" / f"year={year}").glob("*.parquet"))
            after = sum(f.stat().st_size for f in after_files)
            total_after += after
            print(f"  -> {after/1e6:.1f} MB (saved {(before-after)/1e6:.1f} MB, rows unchanged: {rows})")
        migrated += 1

print()
print(f"partitions to migrate: {migrated}, already slim: {skipped}, rows: {total_rows}")
if args.apply:
    print(f"bytes before {total_before/1e9:.3f} GB -> after {total_after/1e9:.3f} GB "
          f"(saved {(total_before-total_after)/1e9:.3f} GB)")
    print("note: data_version.json is input-fingerprint based and does not change; "
          "restart the app / flush its response cache.")
else:
    print("dry run; pass --apply to rewrite")
