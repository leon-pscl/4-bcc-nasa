from pathlib import Path

from legacy.compare import analysis_bundle

SAMPLE = Path(__file__).resolve().parents[1] / "sample-data"


def test_legacy_reference_checks_pass():
    bundle = analysis_bundle(SAMPLE / "modis.csv", SAMPLE / "viirs.csv")
    checks = bundle["checks"]
    applicable = [c for c in checks if c["ok"] is not None]
    assert applicable, "no applicable checks"
    for c in applicable:
        assert c["ok"] is True, f"failed: {c['label']} got {c['computed']} want {c['expected']}"