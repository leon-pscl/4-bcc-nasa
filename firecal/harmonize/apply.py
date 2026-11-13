"""Build harmonized series from cell-days."""

import pandas as pd

from firecal.contracts import validate_harmonized


def build_harmonized(celldays, calibration, settings):
    start = pd.to_datetime(settings.SERIES_START).date()
    switch = pd.to_datetime(settings.SWITCH_DATE).date()
    cd = celldays.copy()
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    cd = cd[cd["date_local"] >= start].copy()

    cal = calibration.copy()
    # ensure month int
    cal["month"] = cal["month"].astype(int)

    def lookup_k(tile, month):
        # tile+month
        sub = cal[(cal["tile_id"] == tile) & (cal["month"] == month)]
        if len(sub):
            return float(sub.iloc[0]["k"])
        sub = cal[(cal["tile_id"] == tile) & (cal["month"] == 0)]
        if len(sub):
            return float(sub.iloc[0]["k"])
        sub = cal[(cal["tile_id"] == "ALL") & (cal["month"] == month)]
        if len(sub):
            return float(sub.iloc[0]["k"])
        sub = cal[(cal["tile_id"] == "ALL") & (cal["month"] == 0)]
        if len(sub):
            return float(sub.iloc[0]["k"])
        raise ValueError("no calibration factor found")

    rows = []
    # pre-switch Aqua
    pre = cd[(cd["date_local"] < switch) & (cd["platform"] == "Aqua")].copy()
    if len(pre):
        pre["month"] = pd.to_datetime(pre["date_local"]).dt.month
        pre["k"] = [lookup_k(t, m) for t, m in zip(pre["tile_id"], pre["month"])]
        pre_out = pd.DataFrame({
            "cell_lat_idx": pre["cell_lat_idx"].astype(int),
            "cell_lon_idx": pre["cell_lon_idx"].astype(int),
            "tile_id": pre["tile_id"],
            "date_local": pre["date_local"],
            "value": pre["k"].astype(float),
            "basis": "modis_scaled",
        })
        rows.append(pre_out)

    # post-switch SNPP
    post = cd[(cd["date_local"] >= switch) & (cd["platform"] == "SNPP")].copy()
    if len(post):
        post_out = pd.DataFrame({
            "cell_lat_idx": post["cell_lat_idx"].astype(int),
            "cell_lon_idx": post["cell_lon_idx"].astype(int),
            "tile_id": post["tile_id"],
            "date_local": post["date_local"],
            "value": 1.0,
            "basis": "viirs",
        })
        rows.append(post_out)

    # gap fill
    if len(cd[cd["date_local"] >= switch]):
        post_dates = sorted(set(cd[cd["date_local"] >= switch]["date_local"]))
        # platforms per date
        plat_by_date = cd[cd["date_local"] >= switch].groupby("date_local")["platform"].agg(lambda s: set(s))
        aqua_post = cd[(cd["date_local"] >= switch) & (cd["platform"] == "Aqua")].copy()
        if len(aqua_post):
            aqua_post["month"] = pd.to_datetime(aqua_post["date_local"]).dt.month
            aqua_post["k"] = [lookup_k(t, m) for t, m in zip(aqua_post["tile_id"], aqua_post["month"])]
            gap_dates = [d for d in post_dates if "SNPP" not in plat_by_date.get(d, set()) and "Aqua" in plat_by_date.get(d, set())]
            if gap_dates:
                gap_df = aqua_post[aqua_post["date_local"].isin(gap_dates)]
                gap_out = pd.DataFrame({
                    "cell_lat_idx": gap_df["cell_lat_idx"].astype(int),
                    "cell_lon_idx": gap_df["cell_lon_idx"].astype(int),
                    "tile_id": gap_df["tile_id"],
                    "date_local": gap_df["date_local"],
                    "value": gap_df["k"].astype(float),
                    "basis": "modis_gapfill",
                })
                rows.append(gap_out)

    if rows:
        out = pd.concat(rows, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["cell_lat_idx", "cell_lon_idx", "tile_id", "date_local", "value", "basis"])

    if len(out):
        out["cell_lat_idx"] = out["cell_lat_idx"].astype("int32")
        out["cell_lon_idx"] = out["cell_lon_idx"].astype("int32")
        out["tile_id"] = out["tile_id"].astype("string")
        out["date_local"] = pd.to_datetime(out["date_local"]).dt.date
        out["value"] = out["value"].astype("float64")
        out["basis"] = out["basis"].astype("string")
    validate_harmonized(out)
    return out