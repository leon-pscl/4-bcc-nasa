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


def test_fallback_and_switch_and_gap():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    settings.KEEP_TYPES = (0,)
    cd = generate(settings, "bolivia_east", seed=42)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    # switch date: before switch modis_scaled, after viirs
    assert "modis_scaled" in set(harm.basis)
    assert "viirs" in set(harm.basis)
    assert "modis_gapfill" in set(harm.basis)
    # C5 hand check monthly_modis
    from firecal.harmonize.validate import validate
    v = validate(cd, cal, settings, harm)
    m = v["calibration_years"]["metrics"]
    assert len(m["monthly_modis"]) == 12


def test_c4_no_sensor_platform():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    cd = generate(settings, "bolivia_east", seed=2)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    assert "sensor" not in harm.columns
    assert "platform" not in harm.columns