"""CLI for firecal.ingest."""

import argparse
import glob
import json
import os
import sys

import pandas as pd

from firecal.config import Settings
from firecal.ingest.firms_csv import read_firms_csv
from firecal.ingest.store import merge_into_store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region")
    parser.add_argument("--bbox")
    parser.add_argument("--name")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    settings = Settings.from_env()
    store_path = os.path.join(settings.DATA_PROCESSED, "detections.parquet")
    os.makedirs(settings.DATA_PROCESSED, exist_ok=True)

    if args.files:
        paths = []
        for pat in args.files:
            paths.extend(glob.glob(pat))
        frames = [read_firms_csv(p) for p in paths]
        if not frames:
            print("no files")
            sys.exit(1)
        new_df = pd.concat(frames, ignore_index=True)
        merge_into_store(new_df, store_path)
        print(f"ingested {len(new_df)} rows")
        return

    # ingest from manifest
    manifest_path = os.path.join(settings.DATA_RAW, "firms", "manifest.jsonl")
    if not os.path.exists(manifest_path):
        print("no manifest")
        sys.exit(1)
    entries = [json.loads(l) for l in open(manifest_path) if l.strip()]
    if args.region:
        bbox = settings.REGIONS[args.region]
    elif args.bbox:
        bbox = tuple(float(x) for x in args.bbox.split(","))
    else:
        print("need --region or --bbox or files")
        sys.exit(1)
    matching = [e for e in entries if tuple(e["bbox"]) == tuple(bbox)]
    frames = []
    for e in matching:
        frames.append(read_firms_csv(e["path"]))
    if not frames:
        print("no matching manifest entries")
        sys.exit(1)
    new_df = pd.concat(frames, ignore_index=True)
    dates = [e["date"] for e in matching]
    # expand to actual chunk dates? use manifest date only (start of chunk); approximate
    all_dates = []
    for e in matching:
        from datetime import date, timedelta
        d = date.fromisoformat(e["date"])
        for i in range(e["day_range"]):
            all_dates.append(d + timedelta(days=i))
    start = min(all_dates).isoformat() if all_dates else None
    end = max(all_dates).isoformat() if all_dates else None
    platforms = sorted(set(new_df["platform"].astype(str))) if len(new_df) else []
    coverage_path = os.path.join(settings.DATA_PROCESSED, "coverage.json")
    entry = {
        "name": args.region or args.name or "custom",
        "bbox": list(bbox),
        "start": start,
        "end": end,
        "platforms": platforms,
        "latest_date": end,
        "synthetic": False,
    }
    merge_into_store(new_df, store_path, coverage_path=coverage_path, coverage_entry=entry)
    print(f"ingested {len(new_df)} rows")


if __name__ == "__main__":
    main()