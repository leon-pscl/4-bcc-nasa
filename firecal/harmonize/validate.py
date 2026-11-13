"""Validation metrics for harmonization."""

import json
import os

import numpy as np
import pandas as pd

from firecal.harmonize.calibrate import fit_calibration


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


def _monthly(cd, cal, years, platform_filter=None):
    # returns dict year -> (viirs list, modis list)
    result = {}
    all_viirs = []
    all_modis = []
    for y in years:
        mv = [0.0] * 12
        mm = [0.0] * 12
        # viirs cell-days
        snpp = cd[(cd["platform"] == "SNPP")]
        snpp = snpp[pd.to_datetime(snpp["date_local"]).dt.year == y]
        for m in range(1, 13):
            mv[m-1] = float(len(snpp[pd.to_datetime(snpp["date_local"]).dt.month == m]))
        # modis = aqua cell-days x k
        aqua = cd[(cd["platform"] == "Aqua")]
        aqua = aqua[pd.to_datetime(aqua["date_local"]).dt.year == y]
        for m in range(1, 13):
            sub = aqua[pd.to_datetime(aqua["date_local"]).dt.month == m]
            total = 0.0
            for _, r in sub.iterrows():
                total += _lookup_k(cal, r["tile_id"], m)
            mm[m-1] = total
        result[y] = {"monthly_viirs": mv, "monthly_modis": mm}
        all_viirs.extend(mv)
        all_modis.extend(mm)
    # overall metrics
    idx = [i for i in range(len(all_viirs)) if all_viirs[i] >= 10]
    if len(idx) >= 2:
        v = np.array([all_viirs[i] for i in idx], dtype=float)
        marr = np.array([all_modis[i] for i in idx], dtype=float)
        r = float(np.corrcoef(v, marr)[0, 1]) if v.std() > 0 and marr.std() > 0 else 0.0
        bias = float((marr.mean() - v.mean()) / v.mean() * 100) if v.mean() != 0 else 0.0
        mape = float(np.median(np.abs((marr - v) / np.where(v == 0, 1, v)) * 100))
    else:
        r, bias, mape = 0.0, 0.0, 0.0
    overall = {"r": r, "bias_pct": bias, "median_abs_pct_error": mape}
    return result, overall


def validate(celldays, calibration, settings, harmonized=None):
    cal_years = list(range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1))
    val_years = list(range(settings.VALIDATION_YEARS[0], settings.VALIDATION_YEARS[1] + 1))
    cal_res, cal_overall = _monthly(celldays, calibration, cal_years)
    val_res, val_overall = _monthly(celldays, calibration, val_years)
    # overall across both
    all_years = cal_years + val_years
    _, all_overall = _monthly(celldays, calibration, all_years)
    out = {
        "calibration_years": cal_res,
        "validation_years": val_res,
        "overall": all_overall,
    }
    # attach metrics per year
    for label, years in [("calibration_years", cal_years), ("validation_years", val_years)]:
        for y in years:
            mv = out[label][y]["monthly_viirs"]
            mm = out[label][y]["monthly_modis"]
            idx = [i for i in range(12) if mv[i] >= 10]
            if len(idx) >= 2:
                v = np.array([mv[i] for i in idx], dtype=float)
                marr = np.array([mm[i] for i in idx], dtype=float)
                r = float(np.corrcoef(v, marr)[0, 1]) if v.std() > 0 and marr.std() > 0 else 0.0
                bias = float((marr.mean() - v.mean()) / v.mean() * 100) if v.mean() != 0 else 0.0
                mape = float(np.median(np.abs((marr - v) / np.where(v == 0, 1, v)) * 100))
            else:
                r, bias, mape = 0.0, 0.0, 0.0
            out[label][y]["r"] = r
            out[label][y]["bias_pct"] = bias
            out[label][y]["median_abs_pct_error"] = mape
    return out