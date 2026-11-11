"""CLI for ingesting FIRMS CSVs into detections.parquet."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from firecal.config import Settings
from firecal.fetch.cache import load_manifest, bbox_slug
from firecal.ingest.firms_csv import read_firms_csv
from firecal.ingest.store import merge_into_store, update_coverage


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.ingest")
    parser.add_argument("--region")
    parser.add_argument("--bbox")
    parser.add_argument("--name")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    settings = Settings()
    store_path = Path(settings.DATA_PROCESSED) / "detections.parquet"
    coverage_path = Path(settings.DATA_PROCESSED) / "coverage.json"

    name = args.name or args.region or "custom"
    if args.region:
        if args.region not in settings.REGIONS:
            raise SystemExit(f"unknown region: {args.region}")
        bbox = settings.REGIONS[args.region]
    elif args.bbox:
        bbox = tuple(float(x) for x in args.bbox.split(","))
    else:
        bbox = None

    dfs = []
    if args.files:
        for f in args.files:
            dfs.append(read_firms_csv(f))
    else:
        # ingest from manifest
        manifest = load_manifest(settings.DATA_RAW)
        for entry in manifest:
            if bbox is not None and [round(float(x), 4) for x in entry["bbox"]] != [round(float(x), 4) for x in bbox]:
                continue
            p = Path(entry["path"])
            if p.exists():
                dfs.append(read_firms_csv(p))

    if not dfs:
        print("no files to ingest")
        return 0

    combined = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    merge_into_store(combined, store_path)

    if bbox is not None:
        platforms = sorted(combined["platform"].unique().tolist())
        start = str(combined["date_local"].min())
        end = str(combined["date_local"].max())
        update_coverage(store_path, coverage_path, name, bbox, start, end, platforms, synthetic=False)

    print("ingested rows:", len(combined))
    return 0


if __name__ == "__main__":
    sys.exit(main())