"""CLI for firecal.fetch."""

import argparse
import hashlib
import json
import os
import sys
import time

from firecal.config import Settings
from firecal.fetch.cache import (
    bbox_slug, cache_path, is_fetched, manifest_append, write_atomic,
)
from firecal.fetch.client import FirmsClient, FirmsError
from firecal.fetch.plan import build_plan
from firecal.fetch.ratelimit import RateLimiter


REGIONS = {}


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


def _availability(client):
    # best-effort: return empty dict; SP assumed available to end
    return {}


def cmd_status(args, settings):
    key = settings.FIRMS_MAP_KEY
    if not key:
        print("No FIRMS_MAP_KEY set. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return
    client = FirmsClient(key, settings.FIRMS_BASE_URL)
    print("key: ***")
    print("availability:", client.data_availability("all")[:200])


def cmd_backfill(args, settings):
    if args.region:
        bbox = _region_bbox(settings, args.region)
        name = args.region
    else:
        bbox = tuple(float(x) for x in args.bbox.split(","))
        name = args.name or "custom"
    start = args.start
    end = args.end
    client = FirmsClient(settings.FIRMS_MAP_KEY, settings.FIRMS_BASE_URL)
    avail = _availability(client)
    manifest = _load_manifest_set(settings)
    chunks = build_plan(bbox, start, end, avail, settings, manifest)
    print(f"chunks: {len(chunks)}")
    tx = sum(c.day_range for c in chunks)
    print(f"estimated transactions: {tx}")
    print(f"estimated time (s): {tx / settings.FIRMS_TX_BUDGET * settings.FIRMS_TX_WINDOW:.1f}")
    if args.dry_run:
        return
    if not settings.FIRMS_MAP_KEY:
        print("Missing FIRMS_MAP_KEY. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return
    rl = RateLimiter(settings.FIRMS_TX_BUDGET, settings.FIRMS_TX_WINDOW)
    for c in chunks:
        rl.acquire(c.day_range)
        try:
            text = client.area_csv(c.source, c.bbox, c.day_range, c.date)
        except FirmsError as exc:
            print("error:", exc)
            break
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
    # reuse backfill with end=today
    args.start = None
    args.end = time.strftime("%Y-%m-%d")
    args.dry_run = False
    cmd_backfill(args, settings)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_status = sub.add_parser("status")
    p_backfill = sub.add_parser("backfill")
    p_backfill.add_argument("--region")
    p_backfill.add_argument("--bbox")
    p_backfill.add_argument("--name")
    p_backfill.add_argument("--start", default="2003-01-01")
    p_backfill.add_argument("--end", default="2026-11-10")
    p_backfill.add_argument("--dry-run", action="store_true")
    p_update = sub.add_parser("update")
    p_update.add_argument("--region")
    p_update.add_argument("--all", action="store_true")
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