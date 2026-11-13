"""Calibration factors MODIS -> VIIRS."""

import pandas as pd

from firecal.contracts import validate_calibration


def _k_for(aqua, snpp):
    if aqua == 0:
        return 1.0
    return snpp / aqua


def fit_calibration(celldays, settings):
    cal_years = range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1)
    df = celldays.copy()
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df = df[df["year"].isin(cal_years)]
    # only Aqua and SNPP
    aqua = df[df["platform"] == "Aqua"]
    snpp = df[df["platform"] == "SNPP"]

    # sums per tile+month
    a_sum = aqua.groupby(["tile_id", pd.to_datetime(aqua["date_local"]).dt.month]).agg(modis=("n_detections", "sum")).reset_index()
    a_sum = a_sum.rename(columns={"date_local": "month"})
    s_sum = snpp.groupby(["tile_id", pd.to_datetime(snpp["date_local"]).dt.month]).agg(viirs=("n_detections", "sum")).reset_index()
    s_sum = s_sum.rename(columns={"date_local": "month"})

    merged = pd.merge(a_sum, s_sum, on=["tile_id", "month"], how="outer").fillna(0)

    # all-tile-month and all-tile aggregates for fallback
    all_month = merged.groupby("month").agg(modis=("modis", "sum"), viirs=("viirs", "sum")).reset_index()
    all_all = pd.DataFrame({"modis": [merged["modis"].sum()], "viirs": [merged["viirs"].sum()]})

    rows = []
    tiles = merged["tile_id"].unique()
    months = range(1, 13)
    for tile in tiles:
        for m in months:
            sub = merged[(merged["tile_id"] == tile) & (merged["month"] == m)]
            aqua_cd = int(sub["modis"].sum()) if len(sub) else 0
            snpp_cd = int(sub["viirs"].sum()) if len(sub) else 0
            if aqua_cd >= settings.MIN_CALIBRATION_CELLDAYS:
                k = _k_for(aqua_cd, snpp_cd)
                level = "tile_month"
            else:
                # tile all months
                t_sub = merged[merged["tile_id"] == tile]
                a_t = int(t_sub["modis"].sum())
                s_t = int(t_sub["viirs"].sum())
                if a_t >= settings.MIN_CALIBRATION_CELLDAYS:
                    k = _k_for(a_t, s_t)
                    level = "tile"
                    aqua_cd, snpp_cd = a_t, s_t
                else:
                    # all tiles this month
                    am = all_month[all_month["month"] == m]
                    a_am = int(am["modis"].sum()) if len(am) else 0
                    s_am = int(am["viirs"].sum()) if len(am) else 0
                    if a_am >= settings.MIN_CALIBRATION_CELLDAYS:
                        k = _k_for(a_am, s_am)
                        level = "all_month"
                        aqua_cd, snpp_cd = a_am, s_am
                    else:
                        a_aa = int(all_all["modis"].iloc[0])
                        s_aa = int(all_all["viirs"].iloc[0])
                        k = _k_for(a_aa, s_aa)
                        level = "all"
                        aqua_cd, snpp_cd = a_aa, s_aa
            rows.append({
                "tile_id": tile,
                "month": m,
                "k": float(k),
                "modis_celldays": int(aqua_cd),
                "viirs_celldays": int(snpp_cd),
                "level": level,
            })
    out = pd.DataFrame(rows)
    out["tile_id"] = out["tile_id"].astype("string")
    out["month"] = out["month"].astype("int8")
    out["k"] = out["k"].astype("float64")
    out["modis_celldays"] = out["modis_celldays"].astype("int64")
    out["viirs_celldays"] = out["viirs_celldays"].astype("int64")
    out["level"] = out["level"].astype("string")
    validate_calibration(out)
    return out