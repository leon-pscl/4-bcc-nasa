"""Pipeline chaining."""

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd):
    print(">", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firecal.pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--region", default="bolivia_east")
    u = sub.add_parser("update")
    u.add_argument("--region")
    u.add_argument("--all", action="store_true")
    u.add_argument("--recalibrate", action="store_true")
    args = parser.parse_args(argv)
    region = getattr(args, "region", None) or "bolivia_east"
    if args.cmd == "backfill":
        run([sys.executable, "-m", "firecal.fetch", "backfill", "--region", region])
        run([sys.executable, "-m", "firecal.ingest", "--region", region])
        run([sys.executable, "-m", "firecal.cells"])
        run([sys.executable, "-m", "firecal.harmonize"])
    else:
        run([sys.executable, "-m", "firecal.fetch", "update", "--region", region])
        run([sys.executable, "-m", "firecal.ingest", "--region", region])
        run([sys.executable, "-m", "firecal.cells"])
        run([sys.executable, "-m", "firecal.harmonize"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())