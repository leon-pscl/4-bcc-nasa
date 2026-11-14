"""CLI for firecal.cells: rebuild the changed celldays partitions."""

import argparse
import json
import os
import sys
import time

from firecal.config import Settings
from firecal.dataset import (CELLDAYS, DETECTIONS, HARMONIZED, write_data_versions,
                             acquire_writer_lock, release_writer_lock)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--years", nargs="*", type=int, default=None)
    args = parser.parse_args()
    settings = Settings.from_env()

    from firecal.cells.db import rebuild
    t0 = time.time()
    own = lock_fd is None
    if own:
        lock_fd = acquire_writer_lock(settings)
    try:
        rebuilt = rebuild(settings, region=args.region,
                          force_years=set(args.years) if args.years else None)
        versions = write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])
    finally:
        if own:
            release_writer_lock(lock_fd)
    print(f"rebuilt {len(rebuilt)} celldays partitions in {time.time() - t0:.1f}s")
    print("data_version:", versions)


if __name__ == "__main__":
    main()
