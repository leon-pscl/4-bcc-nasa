import os

from firecal.config import Settings


def test_defaults():
    s = Settings()
    assert s.SERIES_START == "2003-01-01"
    assert s.MAX_AREA_KM2 == 500_000
    assert s.DATA_RAW == "data/raw"


def test_from_env_override(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DATA_RAW=custom/raw\nFIRMS_MAP_KEY=secret123\n")
    monkeypatch.setenv("DATA_RAW", "env/raw")
    s = Settings.from_env(str(env))
    assert s.DATA_RAW == "env/raw"  # real env takes precedence
    assert s.FIRMS_MAP_KEY == "secret123"


def test_repr_hides_key():
    s = Settings(FIRMS_MAP_KEY="supersecret")
    assert "supersecret" not in repr(s)
    assert "supersecret" not in str(s)