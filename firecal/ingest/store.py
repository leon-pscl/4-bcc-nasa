"""Merge detections into the parquet store."""

import json
import os

import pandas as pd

from firecal.contracts import validate_detections


def merge_into_store(new_df, store_path, coverage_path=None):
    validate_detections(new_df)
    if os.path.exists(store_path):
        old = pd.read_parquet(store_path)
        validate_detections(old)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df.copy()

    # For each (platform, UTC date) with any SP rows, drop that day's NRT rows.
    if "acq_datetime_utc" in combined.columns:
        combined["_udate"] = combined["acq_datetime_utc"].dt.date
        # identify SP keys
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

    # dedup by uid
    combined = combined.drop_duplicates(subset=["uid"])

    validate_detections(combined)
    # atomic write
    tmp = store_path + ".tmp"
    combined.to_parquet(tmp, index=False)
    os.replace(tmp, store_path)

    # update coverage.json (simple: record requested area? caller provides)
    if coverage_path:
        pass
    return combined