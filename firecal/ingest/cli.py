"""CLI for firecal.ingest: FIRMS CSV -> detections dataset (C1).

Reads files in chunks with DuckDB and writes Hive-partitioned Parquet
(region, year). Only partitions whose inputs changed are rebuilt.
"""

import argparse
import json
import os
import sys
import time

from firecal.config import Settings
from firecal.dataset import (CELLDAYS, DETECTIONS, HARMONIZED, load_state,
                             write_data_versions, acquire_writer_lock,
                             release_writer_lock)


def main(lock_fd=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--bbox", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.region:
        bbox = settings.REGIONS.get(args.region)
        if bbox is None:
            print("unknown region", args.region)
            sys.exit(1)
        region = args.region
    elif args.bbox:
        if not args.name:
            print("--name required with --bbox")
            sys.exit(1)
        bbox = tuple(float(x) for x in args.bbox.split(","))
        region = args.name
    else:
        print("need --region or --bbox")
        sys.exit(1)

    from firecal.ingest.db import connect, expand, ingest_files
    own = lock_fd is None
    if own:
        lock_fd = acquire_writer_lock(settings)
    try:
        con = connect()
        paths = expand(args.files)
        if not paths:
            print("no files")
            sys.exit(1)
        t0 = time.time()
        written, rows = ingest_files(con, paths, region, bbox, settings,
                                      dry_run=args.dry_run)
        print(f"rows: {rows}, partitions written: {len(written)}, time {time.time() - t0:.1f}s")
        if written:
            print("partitions:", written[:10], "..." if len(written) > 10 else "")
        write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])
    finally:
        if own:
            release_writer_lock(lock_fd)


if __name__ == "__main__":
    main()
