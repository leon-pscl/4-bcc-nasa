"""Calibration factors MODIS -> VIIRS."""

import pandas as pd

from firecal.contracts import validate_calibration


def fit_calibration(celldays, settings):
    cal_years = range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1)
    df = celldays.copy()
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df = df[df["year"].isin(cal_years)]
    if df.empty:
        raise ValueError("no calibration years present in data")
    aqua = df[df["platform"] == "Aqua"]
    snpp = df[df["platform"] == "SNPP"]
    if aqua.empty:
        raise ValueError("no Aqua cell-days in calibration years")

    # cell-day counts
    a_counts = aqua.groupby(["tile_id", pd.to_datetime(aqua["date_local"]).dt.month]).size().rename("aqua_cd")
    s_counts = snpp.groupby(["tile_id", pd.to_datetime(snpp["date_local"]).dt.month]).size().rename("snpp_cd")
    merged = pd.concat([a_counts, s_counts], axis=1).fillna(0).reset_index()
    merged = merged.rename(columns={"date_local": "month"})

    tile_totals = merged.groupby("tile_id").agg(aqua=("aqua_cd", "sum"), snpp=("snpp_cd", "sum"))
    month_totals = merged.groupby("month").agg(aqua=("aqua_cd", "sum"), snpp=("snpp_cd", "sum"))
    grand_a = int(merged["aqua_cd"].sum())
    grand_s = int(merged["snpp_cd"].sum())

    def k_ratio(a, s):
        if a == 0:
            raise ValueError("cannot calibrate: zero Aqua cell-days")
        return s / a

    rows = []
    tiles = sorted(df["tile_id"].unique())
    for tile in tiles:
        tt = tile_totals.loc[tile] if tile in tile_totals.index else {"aqua": 0, "snpp": 0}
        for m in range(1, 13):
            sub = merged[(merged["tile_id"] == tile) & (merged["month"] == m)]
            a_cd = int(sub["aqua_cd"].sum()) if len(sub) else 0
            s_cd = int(sub["snpp_cd"].sum()) if len(sub) else 0
            if a_cd >= settings.MIN_CALIBRATION_CELLDAYS:
                k = k_ratio(a_cd, s_cd)
                level = "tile_month"
                used_a, used_s = a_cd, s_cd
            elif int(tt["aqua"]) >= settings.MIN_CALIBRATION_CELLDAYS:
                k = k_ratio(int(tt["aqua"]), int(tt["snpp"]))
                level = "tile"
                used_a, used_s = int(tt["aqua"]), int(tt["snpp"])
            else:
                mt = month_totals.loc[m] if m in month_totals.index else {"aqua": 0, "snpp": 0}
                if int(mt["aqua"]) >= settings.MIN_CALIBRATION_CELLDAYS:
                    k = k_ratio(int(mt["aqua"]), int(mt["snpp"]))
                    level = "all_month"
                    used_a, used_s = int(mt["aqua"]), int(mt["snpp"])
                else:
                    k = k_ratio(grand_a, grand_s)
                    level = "all"
                    used_a, used_s = grand_a, grand_s
            rows.append({
                "tile_id": tile,
                "month": m,
                "k": float(k),
                "modis_celldays": int(used_a),
                "viirs_celldays": int(used_s),
                "level": level,
            })

    # ALL rows
    for m in range(1, 13):
        mt = month_totals.loc[m] if m in month_totals.index else {"aqua": 0, "snpp": 0}
        if int(mt["aqua"]) >= settings.MIN_CALIBRATION_CELLDAYS:
            k = k_ratio(int(mt["aqua"]), int(mt["snpp"]))
            level = "all_month"
            ua, us = int(mt["aqua"]), int(mt["snpp"])
        else:
            k = k_ratio(grand_a, grand_s)
            level = "all"
            ua, us = grand_a, grand_s
        rows.append({
            "tile_id": "ALL",
            "month": m,
            "k": float(k),
            "modis_celldays": int(ua),
            "viirs_celldays": int(us),
            "level": level,
        })
    # ALL month 0
    rows.append({
        "tile_id": "ALL",
        "month": 0,
        "k": float(k_ratio(grand_a, grand_s)),
        "modis_celldays": int(grand_a),
        "viirs_celldays": int(grand_s),
        "level": "all",
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