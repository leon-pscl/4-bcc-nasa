"""Settings for the firecal pipeline.

All defaults live here as one ``Settings`` dataclass, so they can be changed
in a single place. Values can be overridden with environment variables (see
``.env.example``).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple


def _load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader (no extra dependency). Existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass
class Settings:
    SERIES_START: str = "2003-01-01"
    MODIS_PLATFORMS: Tuple[str, ...] = ("Aqua",)
    VIIRS_PLATFORMS: Tuple[str, ...] = ("SNPP",)
    SWITCH_DATE: str = "2012-02-01"
    GRID_DEG: float = 0.05
    TILE_DEG: float = 1.0
    CONFIDENCE_KEEP: Tuple[str, ...] = ("nominal", "high")
    KEEP_TYPES: Tuple[int, ...] = (0,)
    DAY_BASIS: str = "local_solar"
    CALIBRATION_YEARS: Tuple[int, int] = (2013, 2017)
    VALIDATION_YEARS: Tuple[int, int] = (2018, 2021)
    MIN_CALIBRATION_CELLDAYS: int = 30
    MIN_BASELINE_YEARS: int = 5
    MAX_AREA_KM2: int = 500_000
    MAX_MAP_CELLS: int = 20_000
    REGIONS: Dict[str, Tuple[float, float, float, float]] = field(
        default_factory=lambda: {
            "bolivia_east": (-64, -18, -60, -14),
            "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738),
        }
    )
    FIRMS_BASE_URL: str = "https://firms.modaps.eosdis.nasa.gov"
    FIRMS_SOURCES: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {
            "MODIS": {"SP": "MODIS_SP", "NRT": "MODIS_NRT"},
            "VIIRS": {"SP": "VIIRS_SNPP_SP", "NRT": "VIIRS_SNPP_NRT"},
        }
    )
    FIRMS_DAY_RANGE_MAX: int = 5
    FIRMS_TX_BUDGET: int = 4000
    FIRMS_TX_WINDOW_S: int = 600
    FIRMS_RETRIES: int = 5
    NRT_REFRESH_DAYS: int = 7
    VIIRS_SP_START: str = "2012-01-20"
    UI_UNIT_LABEL: str = "Hotspots (harmonized)"

    FIRMS_MAP_KEY: str = field(default_factory=lambda: os.getenv("FIRMS_MAP_KEY", ""))
    DATA_RAW: str = field(default_factory=lambda: os.getenv("DATA_RAW", "data/raw"))
    DATA_PROCESSED: str = field(default_factory=lambda: os.getenv("DATA_PROCESSED", "data/processed"))