"""Validation metrics for harmonization."""

import json
import os

import numpy as np
import pandas as pd


def _monthly_totals(cd, harm, years):
    # VIIRS monthly totals from celldays (SNPP)
    snpp = cd[cd["platform"] == "SNPP"].copy()
    snpp["year"] = pd.to_datetime(snpp["date_local"]).dt.year
    snpp["month"] = pd.to_datetime(snpp["date_local"]).dt.month
    # MODIS monthly = Aqua x k from harmonized? Use harmonized modis_scaled
    harm = harm.copy()
    harm["year"] = pd.to_datetime(harm["date_local"]).dt.year
    harm["month"] = pd.to_datetime(harm["date_local"]).dt.month
    modis = harm[harm["basis"].isin(["modis_scaled", "modis_gapfill"])]
    result = {}
    for y in years:
        viirs_monthly = [0.0] * 12
        modis_monthly = [0.0] * 12
        for m in range(1, 13):
            v = snpp[(snpp["year"] == y) & (snpp["month"] == m)]
            # cell-days count = number of rows
            viirs_monthly[m-1] = float(len(v))
            mm = modis[(modis["year"] == y) & (modis["month"] == m)]
            modis_monthly[m-1] = float(mm["value"].sum())
        result[y] = {"monthly_viirs": viirs_monthly, "monthly_modis": modis_monthly}
    return result


def validate(celldays, calibration, settings, harmonized=None):
    cal_years = list(range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1))
    val_years = list(range(settings.VALIDATION_YEARS[0], settings.VALIDATION_YEARS[1] + 1))
    if harmonized is None:
        return {"status": "ok"}
    out = {"calibration_years": {}, "validation_years": {}, "overall": {}}

    def metrics_for_years(years, label):
        monthly_viirs_all = []
        monthly_modis_all = []
        per_year = {}
        for y in years:
            mv = [0.0]*12
            mm = [0.0]*12
            # viirs cell-days per month
            snpp = celldays[celldays["platform"] == "SNPP"].copy()
            snpp["_y"] = pd.to_datetime(snpp["date_local"]).dt.year
            snpp["_m"] = pd.to_datetime(snpp["date_local"]).dt.month
            for m in range(1, 13):
                mv[m-1] = float(len(snpp[(snpp["_y"] == y) & (snpp["_m"] == m)]))
            # modis scaled monthly
            h = harmonized.copy()
            h["_y"] = pd.to_datetime(h["date_local"]).dt.year
            h["_m"] = pd.to_datetime(h["date_local"]).dt.month
            mod = h[(h["basis"].isin(["modis_scaled", "modis_gapfill"])) & (h["_y"] == y)]
            for m in range(1, 13):
                mm[m-1] = float(mod[mod["_m"] == m]["value"].sum())
            # metrics over months where viirs >= 10
            idx = [i for i in range(12) if mv[i] >= 10]
            if len(idx) >= 2:
                v = np.array([mv[i] for i in idx], dtype=float)
                marr = np.array([mm[i] for i in idx], dtype=float)
                r = float(np.corrcoef(v, marr)[0, 1]) if v.std() > 0 and marr.std() > 0 else 0.0
                bias = float((marr.mean() - v.mean()) / v.mean() * 100) if v.mean() != 0 else 0.0
                mape = float(np.median(np.abs((marr - v) / np.where(v == 0, 1, v)) * 100))
            else:
                r, bias, mape = 0.0, 0.0, 0.0
            per_year[y] = {
                "r": r, "bias_pct": bias, "median_abs_pct_error": mape,
                "monthly_viirs": mv, "monthly_modis": mm,
            }
            monthly_viirs_all.extend(mv)
            monthly_modis_all.extend(mm)
        out[label] = per_year
        # overall
        idx = [i for i in range(len(monthly_viirs_all)) if monthly_viirs_all[i] >= 10]
        if len(idx) >= 2:
            v = np.array([monthly_viirs_all[i] for i in idx])
            marr = np.array([monthly_modis_all[i] for i in idx])
            r = float(np.corrcoef(v, marr)[0, 1]) if v.std() > 0 and marr.std() > 0 else 0.0
            bias = float((marr.mean() - v.mean()) / v.mean() * 100) if v.mean() != 0 else 0.0
            mape = float(np.median(np.abs((marr - v) / np.where(v == 0, 1, v)) * 100))
        else:
            r, bias, mape = 0.0, 0.0, 0.0
        out["overall"] = {"r": r, "bias_pct": bias, "median_abs_pct_error": mape}
    metrics_for_years(cal_years, "calibration_years")
    metrics_for_years(val_years, "validation_years")
    return out