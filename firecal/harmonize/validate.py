"""Validation metrics for harmonization."""

import numpy as np
import pandas as pd


def _lookup_k_series(cal, cd):
    # merge k onto celldays rows by tile_id + month, with fallback
    cal = cal.copy()
    cal["month"] = cal["month"].astype(int)
    # build a lookup dict
    lookup = {}
    for _, r in cal.iterrows():
        lookup.setdefault(r["tile_id"], {})[int(r["month"])] = float(r["k"])
    # fallback helpers
    all_month = {m: lookup.get("ALL", {}).get(m) for m in range(1, 13)}
    all_all = lookup.get("ALL", {}).get(0)
    tile_all = {}
    for t, d in lookup.items():
        if t == "ALL":
            continue
        # use month 0 if present else mean
        tile_all[t] = d.get(0, None)
        if tile_all[t] is None and d:
            tile_all[t] = list(d.values())[0]

    def k_for(tile, month):
        d = lookup.get(tile, {})
        if month in d:
            return d[month]
        if 0 in d:
            return d[0]
        if all_month.get(month) is not None:
            return all_month[month]
        if all_all is not None:
            return all_all
        # last resort: any
        for dd in lookup.values():
            if dd:
                return list(dd.values())[0]
        return 1.0

    out = cd.copy()
    months = pd.to_datetime(out["date_local"]).dt.month
    out["_k"] = [k_for(t, m) for t, m in zip(out["tile_id"], months)]
    return out


def _monthly(cd, cal, years):
    cd = cd.copy()
    cd["_date"] = pd.to_datetime(cd["date_local"]).dt.date
    cd["_year"] = pd.to_datetime(cd["date_local"]).dt.year
    cd["_month"] = pd.to_datetime(cd["date_local"]).dt.month

    # outage days: dates with Aqua but no SNPP
    snpp_dates = set(cd[cd["platform"] == "SNPP"]["_date"])
    aqua_dates = set(cd[cd["platform"] == "Aqua"]["_date"])
    outage_dates = aqua_dates - snpp_dates

    aqua = cd[cd["platform"] == "Aqua"].copy()
    aqua = _lookup_k_series(cal, aqua)
    # exclude outage days
    aqua = aqua[~aqua["_date"].isin(outage_dates)]

    # monthly viirs: count SNPP rows
    snpp = cd[cd["platform"] == "SNPP"].copy()
    snpp["_year"] = pd.to_datetime(snpp["date_local"]).dt.year
    snpp["_month"] = pd.to_datetime(snpp["date_local"]).dt.month

    per_year = {}
    all_viirs = []
    all_modis = []
    for y in years:
        mv = [0.0] * 12
        mm = [0.0] * 12
        s_y = snpp[snpp["_year"] == y]
        for m in range(1, 13):
            mv[m - 1] = float(len(s_y[s_y["_month"] == m]))
        a_y = aqua[aqua["_year"] == y]
        for m in range(1, 13):
            mm[m - 1] = float(a_y[a_y["_month"] == m]["_k"].sum())
        per_year[y] = {
            "monthly_viirs": mv,
            "monthly_modis": mm,
        }
        all_viirs.extend(mv)
        all_modis.extend(mm)

    metrics = _metrics(all_viirs, all_modis)
    metrics["monthly_viirs"] = all_viirs
    metrics["monthly_modis"] = all_modis
    for y in years:
        mv = per_year[y]["monthly_viirs"]
        mm = per_year[y]["monthly_modis"]
        per_year[y]["metrics"] = _metrics(mv, mm)
        per_year[y]["metrics"]["monthly_viirs"] = mv
        per_year[y]["metrics"]["monthly_modis"] = mm
    return {
        "years": years,
        "metrics": metrics,
        "per_year": {str(y): per_year[y] for y in years},
    }


def _metrics(mv, mm):
    idx = [i for i in range(len(mv)) if mv[i] >= 10]
    if len(idx) >= 2:
        v = np.array([mv[i] for i in idx], dtype=float)
        marr = np.array([mm[i] for i in idx], dtype=float)
        r = float(np.corrcoef(v, marr)[0, 1]) if v.std() > 0 and marr.std() > 0 else 0.0
        bias = float((marr.mean() - v.mean()) / v.mean() * 100) if v.mean() != 0 else 0.0
        mape = float(np.median(np.abs((marr - v) / np.where(v == 0, 1, v)) * 100))
    else:
        r, bias, mape = 0.0, 0.0, 0.0
    return {"pearson_r": r, "bias_pct": bias, "median_abs_pct_error": mape}


def validate(celldays, calibration, settings, harmonized=None):
    cal_years = list(range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1))
    val_years = list(range(settings.VALIDATION_YEARS[0], settings.VALIDATION_YEARS[1] + 1))
    cal = _monthly(celldays, calibration, cal_years)
    val = _monthly(celldays, calibration, val_years)
    return {
        "calibration_years": cal,
        "validation_years": val,
    }