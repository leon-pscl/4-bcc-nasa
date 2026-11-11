"""CLI for fetching FIRMS data."""

import argparse
import os
import sys
from datetime import date, timedelta

from firecal.config import Settings
from firecal.fetch.cache import (
    append_manifest, count_rows, is_cached, load_manifest, raw_path,
    sha256_text, write_atomic, chunk_end,
)
from firecal.fetch.client import FirmsClient
from firecal.fetch.plan import build_plan
from firecal.fetch.ratelimit import RateLimiter


def _settings():
    return Settings()


def _region_bbox(name, settings):
    if name not in settings.REGIONS:
        raise SystemExit(f"unknown region: {name}")
    return settings.REGIONS[name]


def _parse_bbox(s):
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise SystemExit("bbox must be W,S,E,N")
    return tuple(parts)


def cmd_status(args):
    settings = _settings()
    key = settings.FIRMS_MAP_KEY
    if not key:
        print("FIRMS_MAP_KEY is not set. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return 1
    client = FirmsClient(key, settings.FIRMS_BASE_URL)
    print("key_status:", client.key_status())
    for src in ("MODIS_SP", "VIIRS_SNPP_SP", "MODIS_NRT", "VIIRS_SNPP_NRT"):
        try:
            avail = client.data_availability(src)
            print(src, avail)
        except Exception as exc:
            print(src, "error:", str(exc).replace(key, "***"))
    return 0


def _resolve_area(args, settings):
    if args.region:
        return args.region, _region_bbox(args.region, settings)
    if args.bbox:
        name = args.name or "custom"
        return name, _parse_bbox(args.bbox)
    raise SystemExit("provide --region or --bbox")


def cmd_backfill(args):
    settings = _settings()
    key = settings.FIRMS_MAP_KEY
    if not key:
        print("FIRMS_MAP_KEY is not set. Sign up at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return 1
    name, bbox = _resolve_area(args, settings)
    end = args.end or date.today().isoformat()
    start = args.start or settings.SERIES_START
    client = FirmsClient(key, settings.FIRMS_BASE_URL)
    avail = client.data_availability("all")
    plan = build_plan(bbox, start, end, avail, settings)

    # counts per source
    from collections import Counter

    counts = Counter(c.source for c in plan)
    total_tx = sum(c.day_range for c in plan)
    print("chunks per source:", dict(counts))
    print("total chunks:", len(plan))
    print("estimated transactions:", total_tx)
    print("estimated minutes:", round(total_tx / settings.FIRMS_TX_BUDGET * 10, 1))

    if args.dry_run:
        return 0

    manifest = load_manifest(settings.DATA_RAW)
    rl = RateLimiter(settings.FIRMS_TX_BUDGET, settings.FIRMS_TX_WINDOW_S)
    today = date.today()
    fetched = 0
    for chunk in plan:
        ce = chunk_end(chunk.date, chunk.day_range)
        refresh = False
        if chunk.source.endswith("NRT") and (today - ce).days <= settings.NRT_REFRESH_DAYS:
            refresh = True
        if (not refresh) and is_cached(settings.DATA_RAW, chunk.source, chunk.bbox, chunk.date, chunk.day_range, manifest):
            continue
        rl.acquire(chunk.day_range)
        body = client.area_csv(chunk.source, chunk.bbox, chunk.day_range, chunk.date)
        p = raw_path(settings.DATA_RAW, chunk.source, chunk.bbox, chunk.date, chunk.day_range)
        write_atomic(p, body)
        entry = {
            "source": chunk.source,
            "bbox": [round(float(x), 4) for x in chunk.bbox],
            "date": chunk.date,
            "day_range": chunk.day_range,
            "rows": count_rows(body),
            "sha256": sha256_text(body),
            "fetched_at": datetime_now(),
            "path": str(p),
        }
        append_manifest(settings.DATA_RAW, entry)
        manifest.append(entry)
        fetched += 1
    print("fetched chunks:", fetched)
    return 0


def datetime_now():
    return date.today().isoformat() + "T00:00:00"


def cmd_update(args):
    settings = _settings()
    # reuse backfill with start from last cached date
    manifest = load_manifest(settings.DATA_RAW)
    # find latest date in manifest for region bbox? Simplify: start 7 days back
    args.start = (date.today() - timedelta(days=30)).isoformat()
    args.end = date.today().isoformat()
    args.dry_run = False
    if not args.region and not args.bbox:
        args.region = "bolivia_east"
    return cmd_backfill(args)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.fetch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_status = sub.add_parser("status")
    p_status.set_defaults(func=cmd_status)

    p_back = sub.add_parser("backfill")
    p_back.add_argument("--region")
    p_back.add_argument("--bbox")
    p_back.add_argument("--name")
    p_back.add_argument("--start")
    p_back.add_argument("--end")
    p_back.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_back.set_defaults(func=cmd_backfill, dry_run=False)

    p_upd = sub.add_parser("update")
    p_upd.add_argument("--region")
    p_upd.add_argument("--bbox")
    p_upd.add_argument("--name")
    p_upd.set_defaults(func=cmd_update)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())