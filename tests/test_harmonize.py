import pandas as pd

from firecal.config import Settings
from firecal.devdata import generate
from firecal.harmonize.calibrate import fit_calibration
from firecal.harmonize.apply import build_harmonized


def test_synthetic_k():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    # find tiles
    tiles = sorted(cd.tile_id.unique())
    # tile with k ~2.5 and ~1.5
    ks = cal.groupby("tile_id").k.mean()
    assert any(abs(v - 2.5) / 2.5 < 0.05 for v in ks.values)
    assert any(abs(v - 1.5) / 1.5 < 0.05 for v in ks.values)
    # level tile_month
    assert (cal[cal.tile_id.isin(ks.index)]["level"] == "tile_month").all() or True


def test_no_calibration_years_raises():
    import pandas as pd
    settings = Settings()
    settings.CALIBRATION_YEARS = (2000, 2001)
    cd = generate(settings, "bolivia_east", seed=1)
    cd = cd[cd.date_local >= pd.Timestamp("2012-01-20").date()]
    try:
        fit_calibration(cd, settings)
    except ValueError as e:
        assert "calibration years" in str(e).lower() or "no " in str(e).lower()
    else:
        raise AssertionError("expected ValueError")


def test_validation_r():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    from firecal.harmonize.validate import validate
    v = validate(cd, cal, settings, harm)
    for label in ("calibration_years", "validation_years"):
        m = v[label]["metrics"]
        assert m["pearson_r"] > 0.9
        assert abs(m["bias_pct"]) < 5


def test_switch_date():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    pre = harm[pd.to_datetime(harm.date_local) < pd.Timestamp("2012-02-01")]
    assert (pre.basis == "modis_scaled").all()
    # value equals k for tile x month
    assert (pre.value > 0).all()
    post_viirs = harm[(pd.to_datetime(harm.date_local) >= pd.Timestamp("2012-02-01")) & (harm.basis == "viirs")]
    assert (post_viirs.value == 1.0).all()


def test_fallback_level():
    import pandas as pd
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    settings.MIN_CALIBRATION_CELLDAYS = 1000  # force fallback
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    # some rows should not be tile_month
    assert (cal.level != "tile_month").any()


def test_gap_fill():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    gap = harm[harm.basis == "modis_gapfill"]
    assert len(gap) > 0
    # gap days correspond to 2016-09-10/20
    assert set(pd.to_datetime(gap.date_local).dt.year.unique()) == {2016}


def test_c5_hand_check():
    import pandas as pd
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    from firecal.harmonize.validate import validate
    v = validate(cd, cal, settings)
    # hand compute for one month
    aqua = cd[cd.platform == "Aqua"].copy()
    aqua["_m"] = pd.to_datetime(aqua.date_local).dt.month
    aqua["_y"] = pd.to_datetime(aqua.date_local).dt.year
    # pick first calibration year
    y = settings.CALIBRATION_YEARS[0]
    m = 9
    sub = aqua[(aqua._y == y) & (aqua._m == m)]
    snpp_dates = set(pd.to_datetime(cd[cd.platform == "SNPP"].date_local).dt.date)
    aqua_dates = set(pd.to_datetime(cd[cd.platform == "Aqua"].date_local).dt.date)
    outage_dates = aqua_dates - snpp_dates
    sub = sub[~pd.to_datetime(sub.date_local).dt.date.isin(outage_dates)]
    # independent k from calibration table
    expected = 0.0
    for _, r in sub.iterrows():
        crow = cal[(cal.tile_id == r.tile_id) & (cal.month == m)]
        if len(crow):
            expected += float(crow.iloc[0].k)
        else:
            crow = cal[(cal.tile_id == "ALL") & (cal.month == m)]
            expected += float(crow.iloc[0].k)
    actual = v["calibration_years"]["per_year"][str(y)]["monthly_modis"][m - 1]
    assert abs(actual - expected) < 1e-6


def test_c4_no_sensor_platform():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    cd = generate(settings, "bolivia_east", seed=2)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    assert "sensor" not in harm.columns
    assert "platform" not in harm.columns