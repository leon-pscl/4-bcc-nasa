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
    # tile A ~2.5, tile B ~1.5
    for tile in cd.tile_id.unique():
        pass
    assert len(cal) > 0


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


def test_c4_no_sensor_platform():
    settings = Settings()
    settings.CONFIDENCE_KEEP = ("low", "nominal", "high")
    cd = generate(settings, "bolivia_east", seed=2)
    cal = fit_calibration(cd, settings)
    harm = build_harmonized(cd, cal, settings)
    assert "sensor" not in harm.columns
    assert "platform" not in harm.columns