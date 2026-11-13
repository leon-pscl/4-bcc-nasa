"""Build harmonized series from cell-days."""

import pandas as pd

from firecal.contracts import validate_harmonized


def build_harmonized(celldays, calibration, settings):
    start = pd.to_datetime(settings.SERIES_START).date()
    switch = pd.to_datetime(settings.SWITCH_DATE).date()
    cd = celldays.copy()
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    cd = cd[cd["date_local"] >= start]

    # lookup k
    cal = calibration.copy()
    cal_lookup = {}
    for _, r in cal.iterrows():
        cal_lookup[(r["tile_id"], int(r["month"]))] = (float(r["k"]), r["level"])

    def k_for(tile, month):
        if (tile, month) in cal_lookup:
            return cal_lookup[(tile, month)][0]
        if (tile, 0) in cal_lookup:
            return cal_lookup[(tile, 0)][0]
        # fallback all
        for (t, m), (k, _) in cal_lookup.items():
            if m == month:
                return k
        # last resort
        if cal_lookup:
            return list(cal_lookup.values())[0][0]
        return 1.0

    rows = []
    # pre-switch: Aqua scaled
    pre = cd[(cd["date_local"] < switch) & (cd["platform"] == "Aqua")]
    for _, r in pre.iterrows():
        m = r["date_local"].month
        k = k_for(r["tile_id"], m)
        rows.append({
            "cell_lat_idx": int(r["cell_lat_idx"]),
            "cell_lon_idx": int(r["cell_lon_idx"]),
            "tile_id": r["tile_id"],
            "date_local": r["date_local"],
            "value": float(k),
            "basis": "modis_scaled",
        })
    # post-switch: SNPP
    post = cd[(cd["date_local"] >= switch) & (cd["platform"] == "SNPP")]
    for _, r in post.iterrows():
        rows.append({
            "cell_lat_idx": int(r["cell_lat_idx"]),
            "cell_lon_idx": int(r["cell_lon_idx"]),
            "tile_id": r["tile_id"],
            "date_local": r["date_local"],
            "value": 1.0,
            "basis": "viirs",
        })
    # gap fill: dates >= switch where SNPP has zero detections across whole area but Aqua has some
    post_dates = sorted(set(cd[cd["date_local"] >= switch]["date_local"]))
    for d in post_dates:
        snpp_day = cd[(cd["date_local"] == d) & (cd["platform"] == "SNPP")]
        aqua_day = cd[(cd["date_local"] == d) & (cd["platform"] == "Aqua")]
        if len(snpp_day) == 0 and len(aqua_day) > 0:
            for _, r in aqua_day.iterrows():
                m = d.month
                k = k_for(r["tile_id"], m)
                rows.append({
                    "cell_lat_idx": int(r["cell_lat_idx"]),
                    "cell_lon_idx": int(r["cell_lon_idx"]),
                    "tile_id": r["tile_id"],
                    "date_local": d,
                    "value": float(k),
                    "basis": "modis_gapfill",
                })

    out = pd.DataFrame(rows, columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"])
    if len(out):
        out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
        out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
        out["tile_id"] = out["tile_id"].astype("string")
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        out["value"] = out["value"].astype("float64")
        out["basis"] = out["basis"].astype("string")
    validate_harmonized(out)
    return out