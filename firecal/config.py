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
    SHRINK_M: int = 30
    SNPP_END: str = "2026-11-02"
    MIN_BASELINE_YEARS: int = 5
    MAX_AREA_KM2: int = 500_000
    MAX_MAP_CELLS: int = 20_000
    REGIONS: dict = field(default_factory=dict)
    STARTER_AREAS: dict = field(default_factory=dict)

    def __post_init__(self):
        try:
            import json, os
            p = os.path.join("config", "regions.json")
            if os.path.exists(p):
                data = json.load(open(p))
                self.REGIONS = {r["name"]: tuple(r["bbox"]) for r in data["regions"]}
                self.STARTER_AREAS = {s["name"]: tuple(s["bbox"]) for s in data["starter_areas"]}
        except Exception:
            if not self.REGIONS:
                self.REGIONS = {"bolivia_east": (-64, -18, -60, -14)}
            if not self.STARTER_AREAS:
                self.STARTER_AREAS = {}
    FIRMS_BASE_URL: str = "https://firms.modaps.eosdis.nasa.gov"
    FIRMS_SOURCES: dict = field(default_factory=lambda: {
        "MODIS": ("MODIS_SP", "MODIS_NRT"),
        "VIIRS": ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
        "NOAA20": ("VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
        "NOAA21": ("VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"),
    })
    FIRMS_DAY_RANGE_MAX: int = 5
    FIRMS_TX_BUDGET: int = 4000
    FIRMS_TX_WINDOW: int = 600
    FIRMS_RETRIES: int = 5
    FIRMS_BACKOFF_BASE_S: int = 5
    NRT_REFRESH_DAYS: int = 7
    VIIRS_SP_START: str = "2012-01-20"
    NOAA20_SP_START: str = "2018-04-01"
    NOAA21_SP_START: str = "2023-03-01"
    API_CACHE_MB: int = 32

    DATA_RAW: str = "data/raw"
    DATA_PROCESSED: str = "data/processed"
    FIRMS_MAP_KEY: str = field(default="", repr=False)
    DUCKDB_WEB_MEMORY_LIMIT: str = "1GB"
    DUCKDB_WEB_THREADS: int = 2
    DUCKDB_PIPELINE_MEMORY_LIMIT: str = "2GB"
    DUCKDB_PIPELINE_THREADS: int = 4
    DUCKDB_TEMP_DIR: str = "/tmp/duckdb"
    DUCKDB_MAX_TEMP_DIRECTORY_SIZE: str = "20GB"

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Settings":
        file_values = _read_env(Path(env_path))
        s = cls()
        s.DATA_RAW = os.environ.get("DATA_RAW", file_values.get("DATA_RAW", s.DATA_RAW))
        s.DATA_PROCESSED = os.environ.get("DATA_PROCESSED", file_values.get("DATA_PROCESSED", s.DATA_PROCESSED))
        s.FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", file_values.get("FIRMS_MAP_KEY", s.FIRMS_MAP_KEY))
        cache_mb = os.environ.get("API_CACHE_MB", file_values.get("API_CACHE_MB"))
        if cache_mb:
            try:
                s.API_CACHE_MB = int(cache_mb)
            except ValueError:
                pass
        for key in ("DUCKDB_WEB_MEMORY_LIMIT", "DUCKDB_PIPELINE_MEMORY_LIMIT", "DUCKDB_TEMP_DIR",
                    "DUCKDB_MAX_TEMP_DIRECTORY_SIZE"):
            val = os.environ.get(key, file_values.get(key))
            if val:
                setattr(s, key, val)
        for key in ("DUCKDB_WEB_THREADS", "DUCKDB_PIPELINE_THREADS"):
            val = os.environ.get(key, file_values.get(key))
            if val:
                try:
                    setattr(s, key, int(val))
                except ValueError:
                    pass
        from firecal.dataset import validate_duckdb_temp_dir
        validate_duckdb_temp_dir(s)
        return s
