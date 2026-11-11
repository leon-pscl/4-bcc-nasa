"""Build the harmonized daily series (C4)."""

from datetime import date

import numpy as np
import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_harmonized


def _k_lookup_series(calibration, tile_series, month_series):
    # map tile+month to k; fallback ALL
    cal = calibration.copy()
    cal["month"] = cal["month"].astype(int)
    lookup = cal.set_index(["tile_id", "month"])["k"]
    all_k = cal[cal["tile_id"] == "ALL"]
    all_val = float(all_k.iloc[0]["k"]) if not all_k.empty else 1.0
    keys = list(zip(tile_series.tolist(), month_series.tolist()))
    out = []
    for t, m in keys:
        if (t, m) in lookup.index:
            out.append(float(lookup.loc[(t, m)]))
        elif (t, 0) in lookup.index:
            out.append(float(lookup.loc[(t, 0)]))
        else:
            out.append(all_val)
    return np.array(out, dtype=float)


def build_harmonized(celldays, calibration, settings=None):
    if settings is None:
        settings = Settings()
    series_start = pd.to_datetime(settings.SERIES_START).date()
    switch_date = pd.to_datetime(settings.SWITCH_DATE).date()

    cd = celldays.copy()
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    cd = cd[cd["date_local"] >= series_start].copy()
    cd["month"] = pd.to_datetime(cd["date_local"]).astype(str).str[5:7].astype(int)
    # Actually month from date
    cd["month"] = pd.to_datetime(cd["date_local"]).dt.month

    out_frames = []

    # Aqua before switch
    aqua = cd[(cd["platform"] == "Aqua") & (cd["date_local"].apply(lambda d: series_start <= d < switch_date))].copy()
    if not aqua.empty:
        aqua["k"] = _k_lookup_series(calibration, aqua["tile_id"], aqua["month"])
        aqua["value"] = aqua["k"]
        aqua["basis"] = "modis_scaled"
        out_frames.append(aqua[["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"]])

    # SNPP on/after switch
    snpp = cd[(cd["platform"] == "SNPP") & (cd["date_local"].apply(lambda d: d >= switch_date))].copy()
    if not snpp.empty:
        snpp["value"] = 1.0
        snpp["basis"] = "viirs"
        out_frames.append(snpp[["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"]])

    # gap fill
    if getattr(settings, "GAPFILL_ENABLED", False):
        snpp_dates = set(snpp["date_local"].tolist()) if not snpp.empty else set()
        aqua_after = cd[(cd["platform"] == "Aqua") & (cd["date_local"].apply(lambda d: d >= switch_date))].copy()
        # dates where snpp zero across all coverage and aqua >= min
        aqua_date_counts = aqua_after.groupby("date_local").size()
        for d, cnt in aqua_date_counts.items():
            if d in snpp_dates:
                continue
            if cnt < getattr(settings, "GAPFILL_MIN_AQUA_CELLDAYS", 20):
                continue
            sub = aqua_after[aqua_after["date_local"] == d].copy()
            sub["month"] = pd.to_datetime(sub["date_local"]).dt.month
            sub["k"] = _k_lookup_series(calibration, sub["tile_id"], sub["month"])
            sub["value"] = sub["k"]
            sub["basis"] = "modis_gapfill"
            out_frames.append(sub[["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"]])

    if out_frames:
        out = pd.concat(out_frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"])

    out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
    out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
    out["tile_id"] = out["tile_id"].astype(str)
    out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
    out["value"] = out["value"].astype("float64")
    out["basis"] = out["basis"].astype(str)
    validate_harmonized(out)
    return out