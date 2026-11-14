"""Stage 7: pipeline orchestrator.

Chains the stages (fetch -> ingest -> cells -> harmonize) into one run. Each step
is the same function its stage's CLI calls; this module only chains them and
stops at the first failure with a clear message. The writer lock is held for the
whole run so no second writer can interleave.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from firecal.config import Settings
from firecal.dataset import (CELLDAYS, DETECTIONS, HARMONIZED, acquire_writer_lock,
                            release_writer_lock, write_data_versions)


def _step(name, fn):
    t0 = time.time()
    try:
        result = fn()
    except SystemExit as exc:
        raise RuntimeError(f"step '{name}' failed (exit {exc.code})") from exc
    except Exception as exc:
        raise RuntimeError(f"step '{name}' failed: {exc}") from exc
    return result, time.time() - t0


def _regions(settings):
    import json as _json
    p = os.path.join("config", "regions.json")
    if not os.path.exists(p):
        return {}
    return {r["name"]: r for r in _json.load(open(p))["regions"]}


def run_add_region(name, settings, summary):
    meta = _regions(settings).get(name)
    if meta is None:
        raise RuntimeError(f"add-region: '{name}' is not in config/regions.json")
    bbox = tuple(meta["bbox"])
    print(f"== add-region {name} (bbox {bbox}) ==")

    # 1. fetch (API backfill for the whole box)
    def fetch():
        from firecal.fetch.cli import cmd_backfill
        import argparse as _ap
        ns = _ap.Namespace(region=None, bbox=",".join(str(x) for x in bbox),
                           name=name, start=None, end=None, dry_run=False)
        cmd_backfill(ns, settings)
    _, d = _step("fetch", fetch)
    summary["steps"].append({"name": "fetch", "duration_s": round(d, 2)})

    # 2. ingest (raw -> detections)
    def ingest():
        from firecal.ingest.cli import main as ingest_main
        import sys as _sys
        argv = _sys.argv[:]
        _sys.argv = ["ingest", "--region", name, "--files", "data/raw/firms/*/*/*.csv"]
        try:
            ingest_main(lock_fd=_lock_fd)
        finally:
            _sys.argv = argv
    _, d = _step("ingest", ingest)
    summary["steps"].append({"name": "ingest", "duration_s": round(d, 2)})

    # 3. cells
    def cells():
        from firecal.cells.cli import main as cells_main
        import sys as _sys
        argv = _sys.argv[:]
        _sys.argv = ["cells", "--region", name]
        try:
            cells_main(lock_fd=_lock_fd)
        finally:
            _sys.argv = argv
    _, d = _step("cells", cells)
    summary["steps"].append({"name": "cells", "duration_s": round(d, 2)})

    # 4. harmonize (with calibration)
    def harmonize():
        from firecal.harmonize.cli import main as harmonize_main
        import sys as _sys
        argv = _sys.argv[:]
        _sys.argv = ["harmonize", "--region", name]
        try:
            harmonize_main(lock_fd=_lock_fd)
        finally:
            _sys.argv = argv
    _, d = _step("harmonize", harmonize)
    summary["steps"].append({"name": "harmonize", "duration_s": round(d, 2)})

    versions = write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])
    summary["data_version"] = versions
    print("data_version:", versions)


def run_update(region, all_regions, settings, recalibrate, summary):
    if all_regions:
        regions = list(settings.REGIONS.keys())
    elif region:
        regions = [region]
    else:
        regions = [None]

    for r in regions:
        print(f"== update {r or 'bbox'} ==")
        # 1. fetch update
        fetched = []
        def fetch():
            nonlocal fetched
            from firecal.fetch.cli import cmd_update
            import argparse as _ap
            ns = _ap.Namespace(region=r, all=False, bbox=None, name=None)
            fetched.extend(cmd_update(ns, settings) or [])
        _, d = _step("fetch", fetch)
        summary["steps"].append({"name": f"fetch:{r}", "duration_s": round(d, 2)})

        # 2. ingest
        def ingest():
            from firecal.ingest.db import ingest_files
            from firecal.config import Settings
            import duckdb
            con = duckdb.connect()
            con.execute("PRAGMA threads=1")
            con.execute("PRAGMA memory_limit='1GB'")
            con.execute("PRAGMA temp_directory='data/processed/_duckdb_tmp'")
            import sys as _sys
            argv = _sys.argv[:]
            files = fetched or ["data/raw/firms/*/*/*.csv"]
            written, rows = ingest_files(con, files, r, settings.REGIONS[r], settings, dry_run=False)
            print(f"rows: {rows}, partitions written: {len(written)}")
            from firecal.dataset import write_data_versions
            write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])
            _sys.argv = argv
        _, d = _step("ingest", ingest)
        summary["steps"].append({"name": f"ingest:{r}", "duration_s": round(d, 2)})

        # 3. cells
        def cells():
            from firecal.cells.cli import main as cells_main
            import sys as _sys
            argv = _sys.argv[:]
            _sys.argv = ["cells", "--region", r]
            try:
                cells_main(lock_fd=_lock_fd)
            finally:
                _sys.argv = argv
        _, d = _step("cells", cells)
        summary["steps"].append({"name": f"cells:{r}", "duration_s": round(d, 2)})

        # 4. harmonize (reuse calibration; refit on request)
        def harmonize():
            from firecal.harmonize.cli import main as harmonize_main
            import sys as _sys
            argv = _sys.argv[:]
            if recalibrate:
                _sys.argv = ["harmonize", "--region", r, "--recalibrate"]
            else:
                _sys.argv = ["harmonize", "--region", r]
            try:
                harmonize_main(lock_fd=_lock_fd)
            finally:
                _sys.argv = argv
        _, d = _step("harmonize", harmonize)
        summary["steps"].append({"name": f"harmonize:{r}", "duration_s": round(d, 2)})

    versions = write_data_versions(settings, [DETECTIONS, CELLDAYS, HARMONIZED])
    summary["data_version"] = versions
    print("data_version:", versions)


def main():
    global _lock_fd
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add-region")
    p_add.add_argument("name")
    p_upd = sub.add_parser("update")
    p_upd.add_argument("--region", default=None)
    p_upd.add_argument("--all", action="store_true")
    p_upd.add_argument("--recalibrate", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    _lock_fd = acquire_writer_lock(settings)

    summary = {
        "cmd": args.cmd,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "data_version": None,
    }
    try:
        if args.cmd == "add-region":
            run_add_region(args.name, settings, summary)
        elif args.cmd == "update":
            run_update(args.region, args.all, settings, args.recalibrate, summary)
    except Exception as exc:
        print(f"pipeline failed: {exc}", file=sys.stderr)
        summary["error"] = str(exc)
        _write_summary(settings, summary)
        release_writer_lock(_lock_fd)
        sys.exit(1)
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_summary(settings, summary)
    release_writer_lock(_lock_fd)
    print("run summary written:", summary["path"])


def _write_summary(settings, summary):
    d = os.path.join(settings.DATA_PROCESSED, "runs")
    os.makedirs(d, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(d, f"{ts}.json")
    summary["path"] = path
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)


_lock_fd = None


if __name__ == "__main__":
    main()