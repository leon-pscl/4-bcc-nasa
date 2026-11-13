"""Validation metrics for harmonization."""

import json
import os

import numpy as np
import pandas as pd


def _lookup_k(cal, tile, month):
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
    raise ValueError("no k")


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


def _monthly(cd, cal, years):
    result_per_year = {}
    all_viirs = []
    all_modis = []
    for y in years:
        mv = [0.0] * 12
        mm = [0.0] * 12
        snpp = cd[cd["platform"] == "SNPP"].copy()
        snpp["_y"] = pd.to_datetime(snpp["date_local"]).dt.year
        snpp["_m"] = pd.to_datetime(snpp["date_local"]).dt.month
        snpp = snpp[snpp["_y"] == y]
        for m in range(1, 13):
            mv[m - 1] = float(len(snpp[snpp["_m"] == m]))
        aqua = cd[cd["platform"] == "Aqua"].copy()
        aqua["_y"] = pd.to_datetime(aqua["date_local"]).dt.year
        aqua["_m"] = pd.to_datetime(aqua["date_local"]).dt.month
        aqua = aqua[aqua["_y"] == y]
        for m in range(1, 13):
            sub = aqua[aqua["_m"] == m]
            total = 0.0
            for _, r in sub.iterrows():
                # leave gap-fill (outage) days out: only modis_scaled-equivalent uses k;
                # here Aqua cell-days x k for all Aqua rows
                total += _lookup_k(cal, r["tile_id"], m)
            mm[m - 1] = total
        result_per_year[y] = {
            "monthly_viirs": mv,
            "monthly_modis": mm,
        }
        all_viirs.extend(mv)
        all_modis.extend(mm)
    # exclude outage months? leave as is; gap days handled by excluding gapfill via harmonized? 
    # We'll keep monthly_modis as Aqua*k (includes outage days). To leave outage days out,
    # subtract gap-fill contribution: recompute mm excluding days where SNPP had 0 across region.
    # Determine outage dates
    snpp_dates = set(pd.to_datetime(cd[cd["platform"] == "SNPP"]["date_local"]).dt.date)
    aqua = cd[cd["platform"] == "Aqua"].copy()
    aqua["_d"] = pd.to_datetime(aqua["date_local"]).dt.date
    aqua["_y"] = pd.to_datetime(aqua["date_local"]).dt.year
    aqua["_m"] = pd.to_datetime(aqua["date_local"]).dt.month
    for y in years:
        mm = [0.0] * 12
        a_y = aqua[aqua["_y"] == y]
        for _, r in a_y.iterrows():
            d = r["_d"]
            # outage day if no SNPP anywhere that day
            snpp_that_day = cd[(cd["platform"] == "SNPP") & (pd.to_datetime(cd["date_local"]).dt.date == d)]
            if len(snpp_that_day) == 0:
                continue  # leave outage day out
            m = r["_m"]
            mm[m - 1] += _lookup_k(cal, r["tile_id"], m)
        result_per_year[y]["monthly_modis"] = mm
        # recompute all_modis
    all_modis = []
    for y in years:
        all_modis.extend(result_per_year[y]["monthly_modis"])
    agg_metrics = _metrics(all_viirs, all_modis)
    per_year_metrics = {}
    for y in years:
        mv = result_per_year[y]["monthly_viirs"]
        mm = result_per_year[y]["monthly_modis"]
        per_year_metrics[y] = _metrics(mv, mm)
        result_per_year[y]["metrics"] = per_year_metrics[y]
    return {
        "years": years,
        "metrics": agg_metrics,
        "per_year": {str(y): {**result_per_year[y], "metrics": per_year_metrics[y]} for y in years},
    }


def validate(celldays, calibration, settings, harmonized=None):
    cal_years = list(range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1))
    val_years = list(range(settings.VALIDATION_YEARS[0], settings.VALIDATION_YEARS[1] + 1))
    cal = _monthly(celldays, calibration, cal_years)
    val = _monthly(celldays, calibration, val_years)
    # overall all years
    all_res = _monthly(celldays, calibration, cal_years + val_years)
    return {
        "calibration_years": cal,
        "validation_years": val,
        "overall": all_res["metrics"],
    }