"""Merge parsed detections into the store (Parquet)."""

import json
from pathlib import Path

import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_detections


def merge_into_store(new_df: pd.DataFrame, store_path) -> pd.DataFrame:
    store_path = Path(store_path)
    if store_path.exists():
        old = pd.read_parquet(store_path)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df.copy()

    # For each (platform, UTC date) with any SP rows, drop that day's NRT rows.
    if "acq_datetime_utc" in combined.columns:
        combined["_date"] = pd.to_datetime(combined["acq_datetime_utc"]).dt.date
    grouped = combined.groupby(["platform", "_date"])["processing"].transform(lambda s: (s == "SP").any())
    mask_drop = (combined["processing"] == "NRT") & grouped
    combined = combined[~mask_drop].copy()
    combined = combined.drop(columns=["_date"])

    # dedup by uid
    combined = combined.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
    validate_detections(combined)

    store_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = store_path.with_suffix(store_path.suffix + ".tmp")
    combined.to_parquet(tmp, index=False)
    tmp.replace(store_path)
    return combined


def update_coverage(store_path, coverage_path, name, bbox, start, end, platforms, synthetic=False):
    coverage_path = Path(coverage_path)
    if coverage_path.exists():
        cov = json.loads(coverage_path.read_text())
    else:
        cov = []
    # remove existing same name
    cov = [c for c in cov if c.get("name") != name]
    cov.append({
        "name": name,
        "bbox": [round(float(x), 4) for x in bbox],
        "start": start,
        "end": end,
        "platforms": list(platforms),
        "latest_date": end,
        "synthetic": synthetic,
    })
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(json.dumps(cov, indent=2))