"""Validation metrics for harmonization (C5)."""

import numpy as np
import pandas as pd
from firecal.config import Settings


def _monthly_totals(celldays, calibration, settings, years):
    # Build harmonized modis scaled for Aqua in those years and compare to SNPP
    cd = celldays.copy()
    cd["date_local"] = pd.to_datetime(cd["date_local"]).dt.date
    cd["year"] = pd.to_datetime(cd["date_local"]).dt.year
    cd["month"] = pd.to_datetime(cd["date_local"]).dt.month
    cd = cd[cd["year"].isin(years)]
    # modis scaled
    aqua = cd[cd["platform"] == "Aqua"]
    snpp = cd[cd["platform"] == "SNPP"]

    # k lookup via calibration (tile/month)
    def k(tile, month):
        sub = calibration[(calibration["tile_id"] == tile) & (calibration["month"].astype(int) == int(month))]
        if not sub.empty:
            return float(sub.iloc[0]["k"])
        sub = calibration[calibration["tile_id"] == "ALL"]
        return float(sub.iloc[0]["k"]) if not sub.empty else 1.0

    aqua = aqua.copy()
    aqua["value"] = aqua.apply(lambda r: k(r["tile_id"], r["date_local"].month), axis=1)
    modis_monthly = aqua.groupby(["year", "month"])["value"].sum()
    viirs_monthly = snpp.groupby(["year", "month"]).size()

    # align
    idx = pd.MultiIndex.from_product([years, range(1, 13)], names=["year", "month"])
    m = modis_monthly.reindex(idx, fill_value=0.0)
    v = viirs_monthly.reindex(idx, fill_value=0)
    return m, v


def validate(celldays, calibration, settings=None):
    if settings is None:
        settings = Settings()
    cal_years = list(range(settings.CALIBRATION_YEARS[0], settings.CALIBRATION_YEARS[1] + 1))
    val_years = list(range(settings.VALIDATION_YEARS[0], settings.VALIDATION_YEARS[1] + 1))

    def metrics_for(years):
        m, v = _monthly_totals(celldays, calibration, settings, years)
        # overall
        mm = m.values.astype(float)
        vv = v.values.astype(float)
        # pearson r over months with any data
        mask = (mm + vv) > 0
        if mask.sum() > 1:
            r = float(np.corrcoef(mm[mask], vv[mask])[0, 1])
        else:
            r = float("nan")
        bias = (mm.sum() - vv.sum()) / vv.sum() if vv.sum() > 0 else float("nan")
        # median abs pct error over months where VIIRS >= 10
        errs = []
        for a, b in zip(mm, vv):
            if b >= 10:
                errs.append(abs(a - b) / b * 100)
        med = float(np.median(errs)) if errs else float("nan")
        return {
            "pearson_r": r,
            "bias_pct": float(bias * 100),
            "median_abs_pct_error": med,
            "monthly_modis": [float(x) for x in mm],
            "monthly_viirs": [float(x) for x in vv],
        }

    return {
        "calibration_years": {
            "years": cal_years,
            "metrics": metrics_for(cal_years),
        },
        "validation_years": {
            "years": val_years,
            "metrics": metrics_for(val_years),
        },
    }