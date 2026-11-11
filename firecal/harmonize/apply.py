"""Build the harmonized daily series (C4)."""

from datetime import date

import pandas as pd

from firecal.config import Settings
from firecal.contracts import validate_harmonized


def _parse(v):
    return pd.to_datetime(v).date() if not isinstance(v, date) else v


def _k_lookup(calibration, tile, month):
    sub = calibration[(calibration["tile_id"] == tile) & (calibration["month"].astype(int) == int(month))]
    if not sub.empty:
        return float(sub.iloc[0]["k"])
    sub = calibration[calibration["tile_id"] == "ALL"]
    if not sub.empty:
        return float(sub.iloc[0]["k"])
    return 1.0


def build_harmonized(celldays, calibration, settings=None):
    if settings is None:
        settings = Settings()
    series_start = pd.to_datetime(settings.SERIES_START).date()
    switch_date = pd.to_datetime(settings.SWITCH_DATE).date()

    cd = celldays.copy()
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    cd = cd[cd["date_local"] >= series_start]

    out_rows = []

    # MODIS scaled (before switch)
    aqua = cd[cd["platform"] == "Aqua"]
    for _, r in aqua.iterrows():
        d = r["date_local"]
        if series_start <= d < switch_date:
            m = d.month
            k = _k_lookup(calibration, r["tile_id"], m)
            out_rows.append({
                "cell_lat_idx": int(r["cell_lat_idx"]),
                "cell_lon_idx": int(r["cell_lon_idx"]),
                "tile_id": r["tile_id"],
                "date_local": d,
                "value": float(k),
                "basis": "modis_scaled",
            })

    # VIIRS (on/after switch)
    snpp = cd[cd["platform"] == "SNPP"]
    snpp_dates = set(snpp["date_local"].tolist())
    for _, r in snpp.iterrows():
        d = r["date_local"]
        if d >= switch_date:
            out_rows.append({
                "cell_lat_idx": int(r["cell_lat_idx"]),
                "cell_lon_idx": int(r["cell_lon_idx"]),
                "tile_id": r["tile_id"],
                "date_local": d,
                "value": 1.0,
                "basis": "viirs",
            })

    # gap fill: dates >= switch where SNPP has zero detections across whole area but Aqua has some
    aqua_dates_after = set(aqua["date_local"].tolist())
    for d in aqua_dates_after:
        if d >= switch_date and d not in snpp_dates:
            sub = aqua[aqua["date_local"] == d]
            for _, r in sub.iterrows():
                m = d.month
                k = _k_lookup(calibration, r["tile_id"], m)
                out_rows.append({
                    "cell_lat_idx": int(r["cell_lat_idx"]),
                    "cell_lon_idx": int(r["cell_lon_idx"]),
                    "tile_id": r["tile_id"],
                    "date_local": d,
                    "value": float(k),
                    "basis": "modis_gapfill",
                })

    out = pd.DataFrame(out_rows, columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"])
    if out.empty:
        # ensure dtypes
        out = pd.DataFrame(columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"])
    out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
    out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
    out["tile_id"] = out["tile_id"].astype(str)
    out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
    out["value"] = out["value"].astype("float64")
    out["basis"] = out["basis"].astype(str)
    validate_harmonized(out)
    return out