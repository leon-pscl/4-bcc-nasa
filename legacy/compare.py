"""
compare.py -- "Harmonization of MODIS and VIIRS Hot Spots" (NASA Space Apps)

What this script does, step by step:

  1. loads modis.csv and viirs.csv and tags every row with a `sensor` column
  2. builds a UTC timestamp from acq_date + acq_time (acq_time is HHMM, e.g. 18 = 00:18)
  3. converts UTC to local solar time: local = utc + (longitude / 15) hours,
     and uses the local date as the row's "day"
  4. harmonizes confidence: MODIS 0-29/30-79/80-100 -> low/nominal/high,
     VIIRS l/n/h -> low/nominal/high (the original value is kept too)
  5. puts both sensors on one shared grid: cell = (floor(lat/GRID), floor(lon/GRID))
  6. for every local day, counts the cells seen by both sensors, MODIS only
     and VIIRS only, plus the raw row counts per sensor
  7. prints a summary (rows, pixel area, confidence split, overlap share)
  8. saves combined.csv and calendar.csv
  9. draws calendar.png (one horizontal stacked bar per day)

Install:   pip install pandas numpy matplotlib
Run:       python compare.py

Note on the "59%" reference number
-----------------------------------
The instructions ask for "the share of MODIS cells also seen by VIIRS, using
only days where both sensors have data".  With the sample files THREE local
days have data from both sensors (27, 28 and 29 Sep), so the headline number
covers those three days: 63.4% (cell-day basis) / 62.5% (cells pooled, still
requiring both sensors on the same day).

The "about 59%" in the instructions is the same statistic restricted to the
two days it names (27-28 Sep): 59.3%.  It is printed as its own reference
check below, so both numbers can be compared side by side.

The same code powers the web app: app.py imports the functions below.
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # "Agg" backend => the chart can be saved without a screen (works in Docker)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
GRID_SIZE = 0.05          # size of one grid cell in degrees (0.05 deg ~ 5.5 km)
SAMPLE_DIR = Path("sample-data")
OUTPUT_DIR = Path("outputs")
MODIS_COLOR = "#3b82f6"   # blue
VIIRS_COLOR = "#f97316"   # orange
BOTH_COLOR = "#22c55e"    # green


# ---------------------------------------------------------------------------
# 1. load the files
# ---------------------------------------------------------------------------
def load_sensor(csv_path, sensor_name):
    """Read one NASA FIRMS CSV and add a `sensor` column.

    The two files are almost identical, but VIIRS names the two brightness
    columns differently (bright_ti4 / bright_ti5 instead of brightness /
    bright_t31).  We rename them so both sensors share the same column names.
    """
    df = pd.read_csv(csv_path)
    if sensor_name == "VIIRS":
        df = df.rename(columns={"bright_ti4": "brightness", "bright_ti5": "bright_t31"})
    df["sensor"] = sensor_name
    return df


def load_both(modis_path, viirs_path):
    """Load the two CSVs and stack them into one table."""
    modis = load_sensor(modis_path, "MODIS")
    viirs = load_sensor(viirs_path, "VIIRS")
    combined = pd.concat([modis, viirs], ignore_index=True)
    return combined


# ---------------------------------------------------------------------------
# 2 + 3. timestamps: UTC first, then local solar time
# ---------------------------------------------------------------------------
def add_timestamps(df, day_mode="local"):
    """Add `utc`, `local` and `day` columns.

    acq_time is an integer in HHMM format, so 18 means 00:18 and 1947 means
    19:47.  Zero-padding to four digits turns it into a time string.

    Local solar time = UTC + (longitude / 15) hours, because the Sun is
    overhead a bit earlier in the east (longitude -15 => one hour earlier).
    """
    # "2026-09-26" + "0018" -> "202609260018"
    date_part = df["acq_date"].astype(str).str.replace("-", "", regex=False)
    time_part = pd.to_numeric(df["acq_time"], errors="coerce").fillna(0).astype("int64").astype(str).str.zfill(4)

    df["utc"] = pd.to_datetime(date_part + time_part, format="%Y%m%d%H%M", errors="coerce")
    df["local"] = df["utc"] + pd.to_timedelta(df["longitude"] / 15.0, unit="h")

    # The "day" we group by.  Local solar date by default, UTC date if asked.
    day_source = df["local"] if day_mode == "local" else df["utc"]
    df["day"] = day_source.dt.strftime("%Y-%m-%d")
    df["hour_local"] = day_source.dt.strftime("%H:%M")
    return df


# ---------------------------------------------------------------------------
# 4. harmonize confidence
# ---------------------------------------------------------------------------
def harmonize_confidence(df):
    """Add `confidence` (low/nominal/high) and keep the raw value in `confidence_raw`.

    MODIS reports a number 0-100, VIIRS reports a letter (l / n / h).
    """
    df["confidence_raw"] = df["confidence"]

    is_modis = df["sensor"] == "MODIS"
    numeric = pd.to_numeric(df["confidence"], errors="coerce")

    # MODIS thresholds: 0-29 low, 30-79 nominal, 80-100 high
    modis_harmonized = pd.Series("nominal", index=df.index, dtype="object")
    modis_harmonized[numeric < 30] = "low"
    modis_harmonized[numeric >= 80] = "high"
    modis_harmonized[numeric.isna()] = "nominal"

    # VIIRS letters: l -> low, n -> nominal, h -> high
    letters = df["confidence"].astype(str).str.lower().str.strip()
    viirs_harmonized = letters.map({"l": "low", "n": "nominal", "h": "high"}).fillna("nominal")

    df["confidence"] = np.where(is_modis, modis_harmonized, viirs_harmonized)
    return df


# ---------------------------------------------------------------------------
# 5. shared grid
# ---------------------------------------------------------------------------
def add_grid_cells(df, grid_size=GRID_SIZE):
    """Put every detection into a grid cell: (floor(lat / grid), floor(lon / grid)).

    floor() matters for negative coordinates: floor(-17.8757 / 0.05) = -358,
    while plain integer truncation would give -357.
    """
    df["cell_lat"] = np.floor(df["latitude"] / grid_size).astype(int)
    df["cell_lon"] = np.floor(df["longitude"] / grid_size).astype(int)
    df["cell"] = df["cell_lat"].astype(str) + "," + df["cell_lon"].astype(str)

    # Pixel area: scan and track are already in km, so scan x track is km^2.
    df["area_km2"] = pd.to_numeric(df["scan"], errors="coerce") * pd.to_numeric(df["track"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# 6. daily cell overlap
# ---------------------------------------------------------------------------
def daily_calendar(df):
    """One row per local day: how many cells each sensor saw and how many they share."""
    rows = []
    for day, group in df.groupby("day"):
        modis_cells = set(group.loc[group["sensor"] == "MODIS", "cell"])
        viirs_cells = set(group.loc[group["sensor"] == "VIIRS", "cell"])
        rows.append(
            {
                "day": day,
                "both": len(modis_cells & viirs_cells),
                "modis_only": len(modis_cells - viirs_cells),
                "viirs_only": len(viirs_cells - modis_cells),
                "modis_rows": int((group["sensor"] == "MODIS").sum()),
                "viirs_rows": int((group["sensor"] == "VIIRS").sum()),
            }
        )
    calendar = pd.DataFrame(rows).sort_values("day").reset_index(drop=True)
    # Flag days where only one sensor reported anything.
    calendar["only_one_sensor"] = (calendar["modis_rows"] == 0) | (calendar["viirs_rows"] == 0)
    return calendar


def cell_day_table(df, grid_size=GRID_SIZE):
    """One row per (day, cell) with the number of MODIS and VIIRS rows in it.

    This is what the web map draws: a cell is "both" when m > 0 and v > 0.
    """
    grouped = df.groupby(["day", "cell", "cell_lat", "cell_lon", "sensor"]).size().unstack("sensor", fill_value=0)
    for col in ("MODIS", "VIIRS"):
        if col not in grouped.columns:
            grouped[col] = 0
    out = grouped.reset_index()[["day", "cell", "cell_lat", "cell_lon", "MODIS", "VIIRS"]]
    out.columns = ["day", "cell", "cell_lat", "cell_lon", "modis_rows", "viirs_rows"]
    # Top-left corner of each cell, in degrees (used as the map rectangle).
    out["lat_min"] = out["cell_lat"] * grid_size
    out["lon_min"] = out["cell_lon"] * grid_size
    return out.sort_values(["day", "cell"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 7. summary numbers
# ---------------------------------------------------------------------------
def overlap_for_days(df, days):
    """Overlap of MODIS cells with VIIRS cells for a list of days.

    Returns both ways of counting it:

    * "cell_day" -- every day is counted separately, so a MODIS cell that
      burned on two days counts twice.  This is the natural reading of
      "for each local day ... the share of MODIS cells also seen by VIIRS".
    * "union"    -- cells are pooled over all the days first, so a cell that
      burned on two days still counts once.
    """
    modis_cell_days = shared_cell_days = 0
    modis_union: set = set()
    shared_union: set = set()
    viirs_union: set = set()

    for day in days:
        group = df[df["day"] == day]
        modis_cells = set(group.loc[group["sensor"] == "MODIS", "cell"])
        viirs_cells = set(group.loc[group["sensor"] == "VIIRS", "cell"])
        modis_cell_days += len(modis_cells)
        shared_cell_days += len(modis_cells & viirs_cells)
        modis_union |= modis_cells
        viirs_union |= viirs_cells
        shared_union |= modis_cells & viirs_cells

    return {
        "cell_day_pct": (100.0 * shared_cell_days / modis_cell_days) if modis_cell_days else 0.0,
        "union_pct": (100.0 * len(shared_union) / len(modis_union)) if modis_union else 0.0,
        "modis_cell_days": modis_cell_days,
        "shared_cell_days": shared_cell_days,
        "modis_union_cells": len(modis_union),
        "shared_union_cells": len(shared_union),
    }


def summary_stats(df, calendar):
    """All the numbers printed at the end (and shown on the web dashboard)."""
    rows_per_sensor = df["sensor"].value_counts().to_dict()

    # Average pixel area (scan x track) per sensor
    avg_area = df.groupby("sensor")["area_km2"].mean().to_dict()

    # low / nominal / high percentage split per sensor
    conf_split = {}
    for sensor, group in df.groupby("sensor"):
        counts = group["confidence"].value_counts()
        total = int(len(group))
        conf_split[sensor] = {
            "low": round(100.0 * float(counts.get("low", 0)) / total, 2),
            "nominal": round(100.0 * float(counts.get("nominal", 0)) / total, 2),
            "high": round(100.0 * float(counts.get("high", 0)) / total, 2),
        }

    # Share of MODIS cells also seen by VIIRS -- using only days where BOTH
    # sensors have data (otherwise the share would be dragged down by days
    # where one sensor simply did not fly over).
    both_days = calendar.loc[~calendar["only_one_sensor"], "day"].tolist()
    overall = overlap_for_days(df, both_days)

    # Per-day overlap, only meaningful on days with both sensors.
    overlap_by_day = {}
    for day in both_days:
        overlap_by_day[day] = round(overlap_for_days(df, [day])["cell_day_pct"], 1)

    return {
        "rows": {k: int(v) for k, v in rows_per_sensor.items()},
        "avg_area_km2": {k: round(float(v), 3) for k, v in avg_area.items()},
        "confidence_split_pct": conf_split,
        # Headline number: cell-day basis over all days where both sensors flew.
        "modis_cells_seen_by_viirs_pct": round(overall["cell_day_pct"], 1),
        "modis_cells_seen_by_viirs_union_pct": round(overall["union_pct"], 1),
        "cells_compared": {
            "shared_cell_days": overall["shared_cell_days"],
            "modis_cell_days": overall["modis_cell_days"],
            "shared_union": overall["shared_union_cells"],
            "modis_union": overall["modis_union_cells"],
        },
        "overlap_pct_by_day": overlap_by_day,
        "both_sensor_days": both_days,
        "days": {
            "total": int(len(calendar)),
            "both_sensors": len(both_days),
            "only_one_sensor": int(calendar["only_one_sensor"].sum()),
        },
        "one_sensor_days": calendar.loc[calendar["only_one_sensor"], "day"].tolist(),
    }


# Reference numbers from docs/agent-instructions.md.  They were produced from
# the two sample files, so they are only a meaningful check for that data.
REFERENCE_DAYS = {"2026-09-27", "2026-09-28"}


def validation_checks(df, summary, calendar):
    """Compare our numbers with the reference values (see docs/agent-instructions.md).

    Every check is {label, expected, computed, ok, note}.  `ok` is None when
    the check does not apply to this dataset (e.g. after uploading other files).
    """
    checks = []
    calendar_days = set(calendar["day"])

    def add(label, computed, expected, tol, note="", fmt="{:.1f}", ok=None):
        if computed is None:
            computed_str = None
        else:
            if ok is None:
                ok = abs(float(computed) - float(expected)) <= tol
            computed_str = fmt.format(computed)
        checks.append(
            {
                "label": label,
                "computed": computed_str,
                "expected": fmt.format(expected),
                "ok": ok,
                "note": note,
            }
        )

    rows = summary["rows"]
    add("MODIS rows", rows.get("MODIS"), 654, 0, fmt="{:.0f}")
    add("VIIRS rows", rows.get("VIIRS"), 2265, 0, fmt="{:.0f}")
    add("MODIS average pixel area (km2)", summary["avg_area_km2"].get("MODIS"), 2.3, 0.1)
    add("VIIRS average pixel area (km2)", summary["avg_area_km2"].get("VIIRS"), 0.21, 0.02, fmt="{:.2f}")

    for sensor, expected in (("MODIS", (1.0, 59.0, 40.0)), ("VIIRS", (10.0, 87.0, 2.5))):
        split = summary["confidence_split_pct"].get(sensor, {})
        if not split:
            continue
        computed = (split.get("low", 0), split.get("nominal", 0), split.get("high", 0))
        ok = all(abs(c - e) <= 1.5 for c, e in zip(computed, expected))
        checks.append(
            {
                "label": f"{sensor} confidence split low/nominal/high (%)",
                "computed": " / ".join(f"{v:.1f}" for v in computed),
                "expected": " / ".join(f"{v:.1f}" for v in expected),
                "ok": ok,
                "note": "",
            }
        )

    # "27 Sep: 73 both, 31 MODIS only, 195 VIIRS only"
    day = calendar[calendar["day"] == "2026-09-27"]
    if len(day):
        row = day.iloc[0]
        ok = (row["both"], row["modis_only"], row["viirs_only"]) == (73, 31, 195)
        checks.append(
            {
                "label": "27 Sep cells: both / MODIS only / VIIRS only",
                "computed": f"{row['both']} / {row['modis_only']} / {row['viirs_only']}",
                "expected": "73 / 31 / 195",
                "ok": ok,
                "note": "",
            }
        )

    # "local days 27-28 Sep: about 59% of MODIS cells also seen by VIIRS"
    if REFERENCE_DAYS.issubset(calendar_days):
        subset = overlap_for_days(df, sorted(REFERENCE_DAYS))["cell_day_pct"]
        add(
            "27-28 Sep: MODIS cells also seen by VIIRS (%)",
            subset,
            59.0,
            1.5,
            note="cell-day basis, exactly the two days named in the instructions",
        )
    else:
        checks.append(
            {
                "label": "27-28 Sep: MODIS cells also seen by VIIRS (%)",
                "computed": None,
                "expected": "59.0",
                "ok": None,
                "note": "those days are not in this dataset",
            }
        )
    return checks


# ---------------------------------------------------------------------------
# 8 + 9. outputs (CSV files + chart)
# ---------------------------------------------------------------------------
def save_outputs(df, calendar, output_dir=OUTPUT_DIR):
    """Save combined.csv, calendar.csv and calendar.png."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_cols = [
        "sensor", "latitude", "longitude", "utc", "local", "day", "hour_local",
        "confidence", "confidence_raw", "cell", "cell_lat", "cell_lon",
        "brightness", "bright_t31", "scan", "track", "area_km2", "frp",
        "satellite", "instrument", "version", "daynight",
    ]
    combined_cols = [c for c in combined_cols if c in df.columns]
    combined = df[combined_cols].copy()
    combined["utc"] = combined["utc"].dt.strftime("%Y-%m-%d %H:%M")
    combined["local"] = combined["local"].dt.strftime("%Y-%m-%d %H:%M")
    combined.to_csv(output_dir / "combined.csv", index=False)

    calendar.to_csv(output_dir / "calendar.csv", index=False)

    plot_calendar(calendar, output_dir / "calendar.png")
    return output_dir


def plot_calendar(calendar, path):
    """One horizontal stacked bar per day: both (green) / MODIS only (blue) / VIIRS only (orange)."""
    fig, ax = plt.subplots(figsize=(10, max(3.0, 0.55 * len(calendar))))
    y = np.arange(len(calendar))
    left_both = np.zeros(len(calendar))

    ax.barh(y, calendar["both"], color=BOTH_COLOR, label="both", left=left_both)
    ax.barh(y, calendar["modis_only"], color=MODIS_COLOR, label="MODIS only", left=left_both + calendar["both"])
    ax.barh(
        y,
        calendar["viirs_only"],
        color=VIIRS_COLOR,
        label="VIIRS only",
        left=left_both + calendar["both"] + calendar["modis_only"],
    )

    ax.set_yticks(y)
    ax.set_yticklabels(calendar["day"])
    ax.invert_yaxis()  # earliest day on top
    ax.set_xlabel("grid cells burned (0.05 deg)")
    ax.set_title("Fire cells per local day: shared vs sensor-only")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Everything above, glued together
# ---------------------------------------------------------------------------
def run_analysis(modis_path, viirs_path, grid_size=GRID_SIZE, day_mode="local"):
    """Run steps 1-6 and return (combined_df, calendar_df, cell_day_df)."""
    df = load_both(modis_path, viirs_path)
    df = add_timestamps(df, day_mode=day_mode)
    df = harmonize_confidence(df)
    df = add_grid_cells(df, grid_size=grid_size)
    calendar = daily_calendar(df)
    cells = cell_day_table(df, grid_size=grid_size)
    return df, calendar, cells


def analysis_bundle(modis_path, viirs_path, grid_size=GRID_SIZE, day_mode="local"):
    """Run the whole analysis and return everything the web app needs.

    Keys: df (pandas), calendar (pandas), cells (pandas), summary, checks, report.
    """
    df, calendar, cells = run_analysis(modis_path, viirs_path, grid_size=grid_size, day_mode=day_mode)
    summary = summary_stats(df, calendar)
    checks = validation_checks(df, summary, calendar)

    # Only the columns the dashboard needs, formatted for humans.
    combined = pd.DataFrame(
        {
            "sensor": df["sensor"],
            "lat": df["latitude"].round(5),
            "lon": df["longitude"].round(5),
            "day": df["day"],
            "utc": df["utc"].dt.strftime("%Y-%m-%d %H:%M"),
            "local": df["local"].dt.strftime("%Y-%m-%d %H:%M"),
            "conf": df["confidence"],
            "conf_raw": df["confidence_raw"].astype(str),
            "cell": df["cell"],
            "frp": pd.to_numeric(df["frp"], errors="coerce").round(2),
            "area": df["area_km2"].round(3),
            "bright": pd.to_numeric(df["brightness"], errors="coerce").round(1),
            "daynight": df.get("daynight", ""),
            "satellite": df.get("satellite", ""),
        }
    )

    report = {
        "settings": {"grid": float(grid_size), "day_mode": day_mode},
        "summary": summary,
        "checks": checks,
        "calendar": calendar.to_dict("records"),
        "cells": cells.to_dict("records"),
        "rows": combined.to_dict("records"),
    }
    return {"df": df, "calendar": calendar, "cells": cells,
            "summary": summary, "checks": checks, "report": report}


def build_report(modis_path, viirs_path, grid_size=GRID_SIZE, day_mode="local"):
    """Same analysis, but returned as plain Python types ready for JSON (web app)."""
    return analysis_bundle(modis_path, viirs_path, grid_size=grid_size, day_mode=day_mode)["report"]


def print_summary(summary, calendar):
    """Print the human-readable summary (step 7)."""
    print("=" * 62)
    print("MODIS vs VIIRS -- hot spot harmonization")
    print("=" * 62)

    print("\nRows per sensor:")
    for sensor in ("MODIS", "VIIRS"):
        print(f"  {sensor:<6} {summary['rows'].get(sensor, 0):>6}")

    print("\nAverage pixel area (scan x track, km2):")
    for sensor in ("MODIS", "VIIRS"):
        print(f"  {sensor:<6} {summary['avg_area_km2'].get(sensor, 0):>6.2f}")

    print("\nConfidence split (%):")
    for sensor in ("MODIS", "VIIRS"):
        split = summary["confidence_split_pct"].get(sensor, {})
        print(
            f"  {sensor:<6} low {split.get('low', 0):>5.1f} / "
            f"nominal {split.get('nominal', 0):>5.1f} / "
            f"high {split.get('high', 0):>5.1f}"
        )

    print("\nMODIS cells also seen by VIIRS (days with both sensors):")
    cells = summary["cells_compared"]
    print(f"  {summary['modis_cells_seen_by_viirs_pct']:>5.1f}%  cell-day basis "
          f"({cells['shared_cell_days']} of {cells['modis_cell_days']} MODIS cell-days)")
    print(f"  {summary['modis_cells_seen_by_viirs_union_pct']:>5.1f}%  union basis "
          f"({cells['shared_union']} of {cells['modis_union']} distinct cells)")
    for day, pct in summary["overlap_pct_by_day"].items():
        print(f"    {day}: {pct:>5.1f}% of that day's MODIS cells also seen by VIIRS")

    print("\nDays:")
    both_days = calendar[~calendar["only_one_sensor"]]
    for _, row in both_days.iterrows():
        print(f"  {row['day']}: both {row['both']:>4} | MODIS only {row['modis_only']:>4} | "
              f"VIIRS only {row['viirs_only']:>4}   (rows {row['modis_rows']}/{row['viirs_rows']})")
    flagged = calendar[calendar["only_one_sensor"]]
    if len(flagged):
        print(f"  flagged (only one sensor): {', '.join(flagged['day'])}")
    print("=" * 62)


def print_checks(checks):
    """Print the reference-value checks (docs/agent-instructions.md)."""
    print("\nReference checks:")
    for check in checks:
        if check["ok"] is None:
            mark = "-"
        else:
            mark = "OK " if check["ok"] else "OFF"
        computed = check["computed"] if check["computed"] is not None else "n/a"
        line = f"  [{mark}] {check['label']:<48} got {computed:>18}  want {check['expected']}"
        if check["note"]:
            line += f"\n         {check['note']}"
        print(line)


def main():
    """Entry point for `python compare.py`."""
    modis_path = SAMPLE_DIR / "modis.csv"
    viirs_path = SAMPLE_DIR / "viirs.csv"
    if not modis_path.exists() or not viirs_path.exists():
        raise SystemExit(f"Put modis.csv and viirs.csv in {SAMPLE_DIR}/ and run me again.")

    bundle = analysis_bundle(modis_path, viirs_path)
    print_summary(bundle["summary"], bundle["calendar"])
    print_checks(bundle["checks"])

    out = save_outputs(bundle["df"], bundle["calendar"], OUTPUT_DIR)
    print(f"\nSaved: {out / 'combined.csv'}, {out / 'calendar.csv'}, {out / 'calendar.png'}")


if __name__ == "__main__":
    main()
