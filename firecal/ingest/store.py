"""Merge detections into the parquet store."""

import json
import os

import pandas as pd

from firecal.contracts import validate_detections


def merge_into_store(new_df, store_path, coverage_path=None, coverage_entry=None):
    validate_detections(new_df)
    if os.path.exists(store_path):
        old = pd.read_parquet(store_path)
        validate_detections(old)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df.copy()

    if "acq_datetime_utc" in combined.columns and len(combined):
        combined["_udate"] = combined["acq_datetime_utc"].dt.date
        sp_keys = set(
            zip(
                combined.loc[combined["processing"] == "SP", "platform"],
                combined.loc[combined["processing"] == "SP", "_udate"],
            )
        )
        mask_nrt_drop = combined.apply(
            lambda r: r["processing"] == "NRT" and (r["platform"], r["_udate"]) in sp_keys,
            axis=1,
        )
        combined = combined[~mask_nrt_drop].copy()
        combined = combined.drop(columns=["_udate"])

    combined = combined.drop_duplicates(subset=["uid"])

    validate_detections(combined)
    tmp = store_path + ".tmp"
    combined.to_parquet(tmp, index=False)
    os.replace(tmp, store_path)

    if coverage_path and coverage_entry:
        _update_coverage(coverage_path, coverage_entry)
    return combined


def _update_coverage(coverage_path, entry):
    if os.path.exists(coverage_path):
        try:
            data = json.load(open(coverage_path))
        except Exception:
            data = []
    else:
        data = []
    # update existing entry by name
    out = []
    replaced = False
    for e in data:
        if e.get("name") == entry.get("name"):
            out.append(entry)
            replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(entry)
    tmp = coverage_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, coverage_path)