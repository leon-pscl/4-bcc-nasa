"""CLI for firecal.outlook: build-grid | build-monthly | issue | backtest."""

import argparse
import time

from firecal.config import Settings
from firecal.dataset import MONTHLY_CELLS, OUTLOOK, DETECTIONS, CELLDAYS, HARMONIZED

_ALL = [DETECTIONS, CELLDAYS, HARMONIZED, MONTHLY_CELLS, OUTLOOK]


def _region(settings, name):
    if name not in settings.REGIONS:
        raise SystemExit(f"unknown region {name!r}; known: {sorted(settings.REGIONS)}")
    return settings.REGIONS[name]


def main():
    parser = argparse.ArgumentParser(prog="firecal.outlook")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build-grid", "build-monthly", "issue", "backtest"):
        p = sub.add_parser(name)
        p.add_argument("--region", required=True)
        p.add_argument("--years", type=int, nargs="*", default=None,
                       help="build-monthly only: limit to these years")
    p_issue = sub.choices["issue"]
    args = parser.parse_args()

    settings = Settings.from_env()
    _region(settings, args.region)
    t0 = time.time()

    if args.cmd == "build-grid":
        from firecal.outlook.surface import build_cell_surface
        from firecal.outlook.cells import build_grid_cells
        from firecal.dataset import write_data_versions
        surf = build_cell_surface(settings, args.region)
        print(f"C10 cell_surface: {len(surf)} rows")
        cells = build_grid_cells(settings, args.region)
        kept = int(cells["keep"].sum())
        print(f"C11 grid_cells: {len(cells)} rows ({kept} kept, {len(cells) - kept} masked)")
        write_data_versions(settings, _ALL)
    elif args.cmd == "build-monthly":
        from firecal.outlook.monthly import build_monthly
        from firecal.dataset import write_data_versions
        meta = build_monthly(settings, args.region, years=args.years)
        print("monthly_cells.meta.json:", {k: meta[k] for k in ("latest_date", "partial_month")})
        write_data_versions(settings, _ALL)
    elif args.cmd == "issue":
        from firecal.outlook.monthly import _latest_date, _partial_month
        from firecal.outlook.issue import build_outlook
        from firecal.dataset import write_data_versions
        latest = _latest_date(settings, args.region)
        if not latest:
            raise SystemExit("no harmonized data; cannot issue")
        print(f"latest_date: {latest} (partial_month={_partial_month(latest)})")
        new, issued, leads = build_outlook(settings, args.region, latest)
        print(f"C14 outlook: {len(new)} rows, issued {issued}")
        write_data_versions(settings, _ALL)
    elif args.cmd == "backtest":
        from firecal.outlook.backtest import build_backtest
        result = build_backtest(settings, args.region)
        print("C16 pooled:", result["pooled"])

    print(f"{args.cmd} done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
