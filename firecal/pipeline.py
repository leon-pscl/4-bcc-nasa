"""Pipeline chaining."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from firecal.config import Settings


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
    settings = Settings()
    proc = Path(settings.DATA_PROCESSED)

    if args.cmd == "backfill":
        region = args.region
        run([sys.executable, "-m", "firecal.fetch", "backfill", "--region", region])
        run([sys.executable, "-m", "firecal.ingest", "--region", region])
        run([sys.executable, "-m", "firecal.cells"])
        run([sys.executable, "-m", "firecal.harmonize"])
        return 0

    # update
    if args.all:
        cov_path = proc / "coverage.json"
        cov = json.loads(cov_path.read_text()) if cov_path.exists() else []
        for c in cov:
            bbox = ",".join(str(x) for x in c["bbox"])
            name = c["name"]
            run([sys.executable, "-m", "firecal.fetch", "update", "--bbox", bbox, "--name", name])
            run([sys.executable, "-m", "firecal.ingest", "--bbox", bbox, "--name", name])
        run([sys.executable, "-m", "firecal.cells"])
        harmonize_cmd = [sys.executable, "-m", "firecal.harmonize"]
        if args.recalibrate or not (proc / "calibration.parquet").exists():
            harmonize_cmd.append("--recalibrate")
        # harmonize cli doesn't accept flag yet; just run
        run([sys.executable, "-m", "firecal.harmonize"])
    else:
        region = args.region or "bolivia_east"
        run([sys.executable, "-m", "firecal.fetch", "update", "--region", region])
        run([sys.executable, "-m", "firecal.ingest", "--region", region])
        run([sys.executable, "-m", "firecal.cells"])
        run([sys.executable, "-m", "firecal.harmonize"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())