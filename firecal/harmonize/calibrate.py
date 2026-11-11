"""Fit MODIS->VIIRS calibration factors."""

import pandas as pd
from firecal.config import Settings


def _filter(celldays, settings):
    years = range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1)
    df = celldays.copy()
    df["year"] = pd.to_datetime(df["date_local"]).dt.year
    df = df[df["year"].isin(years)]
    df = df[df["platform"].isin(["Aqua", "SNPP"])]
    return df


def fit_calibration(celldays, settings=None):
    if settings is None:
        settings = Settings()
    df = _filter(celldays, settings)

    # counts of cell-days
    def counts_by(cols):
        g = df.groupby(cols + ["platform"]).size().unstack(fill_value=0)
        # ensure both columns
        for p in ("Aqua", "SNPP"):
            if p not in g.columns:
                g[p] = 0
        g = g.rename(columns={"Aqua": "modis", "SNPP": "viirs"})
        return g

    tile_month_counts = counts_by(["tile_id", "date_local"]).groupby(level=[0,1]).sum() if False else None
    # simpler: month from date
    df = df.copy()
    df["month"] = pd.to_datetime(df["date_local"]).dt.month

    tm = df.groupby(["tile_id", "month", "platform"]).size().unstack(fill_value=0)
    for p in ("Aqua", "SNPP"):
        if p not in tm.columns:
            tm[p] = 0
    tm = tm.rename(columns={"Aqua": "modis", "SNPP": "viirs"}).reset_index()

    t = df.groupby(["tile_id", "platform"]).size().unstack(fill_value=0)
    for p in ("Aqua", "SNPP"):
        if p not in t.columns:
            t[p] = 0
    t = t.rename(columns={"Aqua": "modis", "SNPP": "viirs"}).reset_index()

    am = df.groupby(["month", "platform"]).size().unstack(fill_value=0)
    for p in ("Aqua", "SNPP"):
        if p not in am.columns:
            am[p] = 0
    am = am.rename(columns={"Aqua": "modis", "SNPP": "viirs"}).reset_index()

    total_modis = int((df["platform"] == "Aqua").sum())
    total_viirs = int((df["platform"] == "SNPP").sum())

    tiles = sorted(df["tile_id"].unique().tolist())
    months = list(range(1, 13))

    tm_lookup = {(row["tile_id"], int(row["month"])): (int(row["modis"]), int(row["viirs"])) for row in tm.to_dict("records")}
    t_lookup = {row["tile_id"]: (int(row["modis"]), int(row["viirs"])) for row in t.to_dict("records")}
    am_lookup = {int(row["month"]): (int(row["modis"]), int(row["viirs"])) for row in am.to_dict("records")}

    rows = []
    for tile in tiles:
        for month in months:
            # level selection
            modis_cm, viirs_cm = tm_lookup.get((tile, month), (0, 0))
            if modis_cm >= settings.MIN_CALIBRATION_CELLDAYS and modis_cm > 0:
                modis, viirs, level = modis_cm, viirs_cm, "tile_month"
            else:
                modis_t, viirs_t = t_lookup.get(tile, (0, 0))
                if modis_t >= settings.MIN_CALIBRATION_CELLDAYS and modis_t > 0:
                    modis, viirs, level = modis_t, viirs_t, "tile"
                else:
                    modis_am, viirs_am = am_lookup.get(month, (0, 0))
                    if modis_am >= settings.MIN_CALIBRATION_CELLDAYS and modis_am > 0:
                        modis, viirs, level = modis_am, viirs_am, "all_month"
                    else:
                        modis, viirs, level = total_modis, total_viirs, "all"
            k = (viirs / modis) if modis > 0 else 1.0
            rows.append({
                "tile_id": tile,
                "month": month,
                "k": float(k),
                "modis_celldays": int(modis),
                "viirs_celldays": int(viirs),
                "level": level,
            })

    # ALL fallback row
    rows.append({
        "tile_id": "ALL",
        "month": 0,
        "k": float(total_viirs / total_modis) if total_modis > 0 else 1.0,
        "modis_celldays": int(total_modis),
        "viirs_celldays": int(total_viirs),
        "level": "all",
    })

    out = pd.DataFrame(rows)
    # month int8
    out["month"] = out["month"].astype("int8")
    from firecal.contracts import validate_calibration
    validate_calibration(out)
    return out