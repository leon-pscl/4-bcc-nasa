"""Settings for the firecal pipeline and web app."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _read_env(path: Path) -> dict:
    """Read a .env file into a dict (no mutation of os.environ)."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


@dataclass
class Settings:
    SERIES_START: str = "2003-01-01"
    MODIS_PLATFORMS: tuple = ("Aqua",)
    VIIRS_PLATFORMS: tuple = ("SNPP",)
    SWITCH_DATE: str = "2012-02-01"
    GRID_DEG: float = 0.05
    TILE_DEG: float = 1.0
    CONFIDENCE_KEEP: tuple = ("nominal", "high")
    KEEP_TYPES: tuple = (0,)
    DAY_BASIS: str = "local_solar"
    CALIBRATION_YEARS: tuple = (2013, 2017)
    VALIDATION_YEARS: tuple = (2018, 2021)
    MIN_CALIBRATION_CELLDAYS: int = 30
    MIN_BASELINE_YEARS: int = 5
    MAX_AREA_KM2: int = 500_000
    MAX_MAP_CELLS: int = 20_000
    REGIONS: dict = field(default_factory=lambda: {
        "bolivia_east": (-64, -18, -60, -14),
        "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738),
    })
    FIRMS_BASE_URL: str = "https://firms.modaps.eosdis.nasa.gov"
    FIRMS_SOURCES: dict = field(default_factory=lambda: {
        "MODIS": ("MODIS_SP", "MODIS_NRT"),
        "VIIRS": ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    })
    FIRMS_DAY_RANGE_MAX: int = 10
    FIRMS_TX_BUDGET: int = 4000
    FIRMS_TX_WINDOW: int = 600
    FIRMS_RETRIES: int = 5
    FIRMS_BACKOFF_BASE_S: int = 5
    NRT_REFRESH_DAYS: int = 7
    VIIRS_SP_START: str = "2012-01-20"

    DATA_RAW: str = "data/raw"
    DATA_PROCESSED: str = "data/processed"
    FIRMS_MAP_KEY: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Settings":
        file_values = _read_env(Path(env_path))
        s = cls()
        s.DATA_RAW = os.environ.get("DATA_RAW", file_values.get("DATA_RAW", s.DATA_RAW))
        s.DATA_PROCESSED = os.environ.get("DATA_PROCESSED", file_values.get("DATA_PROCESSED", s.DATA_PROCESSED))
        s.FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", file_values.get("FIRMS_MAP_KEY", s.FIRMS_MAP_KEY))
        return s
