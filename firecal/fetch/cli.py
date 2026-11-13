"""CLI for firecal.fetch."""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import date

from firecal.config import Settings
from firecal.fetch.cache import (
    bbox_slug, cache_path, is_fetched, manifest_append, write_atomic,
)
from firecal.fetch.client import FirmsClient, FirmsError
from firecal.fetch.plan import build_plan
from firecal.fetch.ratelimit import RateLimiter


def _settings():
    return Settings.from_env()


def _region_bbox(settings, name):
    return settings.REGIONS[name]


def _manifest_path(settings):
    return os.path.join(settings.DATA_RAW, "firms", "manifest.jsonl")


def _load_manifest_set(settings):
    p = _manifest_path(settings)
    s = set()
    if not os.path.exists(p):
        return s
    for line in open(p):
        if not line.strip():
            continue
        e = json.loads(line)
        s.add((e["source"], tuple(e["bbox"]), e["date"], e["day_range"]))
    return s


def _last_cached_date(settings, bbox):
    p = _manifest_path(settings)
    if not os.path.exists(p):
        return None
    dates = []
    for line in open(p):
        if not line.strip():
            continue
        e = json.loads(line)
        if tuple(e["bbox"]) == tuple(bbox):
            dates.append(e["date"])
    if not dates:
        return None
    return max(dates)


def _availability(client):
    raw = client.data_availability("all")
    result = {}
    if isinstance(raw, list):
        for item in raw:
            src = item.get("source") or item.get("Source")
            mn = item.get("min_date") or item.get("start") or item.get("start_date")
            mx = item.get("max_date") or item.get("end") or item.get("end_date")
            if src:
                result[src] = (mn, mx)
    else:
        reader = csv.DictReader(io.StringIO(str(raw)))
        for row in reader:
            src = row.get("data_id") or row.get("source") or row.get("Source")
            mn = row.get("min_date") or row.get("start") or row.get("start_date")
            mx = row.get("max_date") or row.get("end") or row.get("end_date")
            if src:
                result[src] = (mn, mx)
    if not result:
        raise FirmsError("could not parse data availability")
    return result


def cmd_status(args, settings):
    key = settings.FIRMS_MAP_KEY
    if not key:
        print("No FIRMS_MAP_KEY set. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return
    client = FirmsClient(key, settings.FIRMS_BASE_URL)
    print("key: ***")
    avail = _availability(client)
    for src, (mn, mx) in avail.items():
        print(f"{src}: {mn} to {mx}")


def cmd_backfill(args, settings, client=None):
    if args.region:
        bbox = _region_bbox(settings, args.region)
    else:
        bbox = tuple(float(x) for x in args.bbox.split(","))
    start = args.start or settings.SERIES_START
    if args.end:
        end = args.end
    else:
        end = date.today().isoformat()
    today = date.today().isoformat()

    if client is None:
        client = FirmsClient(settings.FIRMS_MAP_KEY, settings.FIRMS_BASE_URL)
    if not settings.FIRMS_MAP_KEY:
        print("Missing FIRMS_MAP_KEY. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        sys.exit(1)
    try:
        avail = _availability(client)
    except FirmsError as exc:
        print("error:", exc)
        sys.exit(1)

    manifest = _load_manifest_set(settings)
    chunks = build_plan(bbox, start, end, avail, settings, manifest, today=today)

    # per-source counts
    from collections import defaultdict
    counts = defaultdict(int)
    txs = defaultdict(int)
    for c in chunks:
        counts[c.source] += 1
        txs[c.source] += c.day_range
    for src in sorted(counts):
        print(f"{src}: {counts[src]} chunks, {txs[src]} transactions")
    print(f"total chunks: {len(chunks)}")
    print(f"total transactions: {sum(txs.values())}")

    if args.dry_run:
        return

    # key status before long run (best-effort; unknown URL must not block fetches)
    try:
        client.key_status()
    except FirmsError as exc:
        print("warning: key_status unavailable:", exc)

    rl = RateLimiter(settings.FIRMS_TX_BUDGET, settings.FIRMS_TX_WINDOW)
    for i, c in enumerate(chunks):
        if i > 0 and i % 500 == 0:
            try:
                client.key_status()
            except FirmsError as exc:
                print("warning: key_status unavailable:", exc)
        rl.acquire(c.day_range)
        try:
            text = client.area_csv(c.source, c.bbox, c.day_range, c.date)
        except FirmsError as exc:
            print("error:", exc)
            sys.exit(1)
        path = cache_path(settings.DATA_RAW, c.source, c.bbox, c.date, c.day_range)
        write_atomic(path, text)
        rows = max(0, len(text.splitlines()) - 1)
        entry = {
            "source": c.source,
            "bbox": list(c.bbox),
            "date": c.date,
            "day_range": c.day_range,
            "rows": rows,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": str(path),
        }
        manifest_append(_manifest_path(settings), entry)


def cmd_update(args, settings):
    if args.all:
        regions = list(settings.REGIONS.keys())
    elif args.region:
        regions = [args.region]
    else:
        regions = [None]
    for r in regions:
        if r is None:
            if not args.bbox:
                print("need --region or --bbox")
                sys.exit(1)
            bbox = tuple(float(x) for x in args.bbox.split(","))
            # reuse backfill args
            ns = argparse.Namespace(
                region=None, bbox=args.bbox, name=args.name,
                start=None, end=None, dry_run=False,
            )
            # start from last cached date
            last = _last_cached_date(settings, bbox)
            ns.start = last if last else settings.SERIES_START
            ns.end = None
            cmd_backfill(ns, settings)
        else:
            bbox = _region_bbox(settings, r)
            ns = argparse.Namespace(
                region=r, bbox=None, name=None,
                start=None, end=None, dry_run=False,
            )
            last = _last_cached_date(settings, bbox)
            ns.start = last if last else settings.SERIES_START
            ns.end = None
            cmd_backfill(ns, settings)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_status = sub.add_parser("status")
    p_backfill = sub.add_parser("backfill")
    p_backfill.add_argument("--region")
    p_backfill.add_argument("--bbox")
    p_backfill.add_argument("--name")
    p_backfill.add_argument("--start", default=None)
    p_backfill.add_argument("--end", default=None)
    p_backfill.add_argument("--dry-run", action="store_true")
    p_update = sub.add_parser("update")
    p_update.add_argument("--region")
    p_update.add_argument("--all", action="store_true")
    p_update.add_argument("--bbox")
    p_update.add_argument("--name")
    args = parser.parse_args()
    settings = _settings()
    if args.cmd == "status":
        cmd_status(args, settings)
    elif args.cmd == "backfill":
        cmd_backfill(args, settings)
    elif args.cmd == "update":
        cmd_update(args, settings)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()