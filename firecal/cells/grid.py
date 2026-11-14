"""Cell and tile helpers."""

import math

import numpy as np

SNAP_DECIMALS = 6


def cell_index(x: float, grid_deg: float) -> int:
    """Cell index along one axis.

    Rounds before flooring, so a coordinate exactly on an edge goes to the cell above it
    (0.3 / 0.05 is 5.999999999999999 in floating point, which would floor to 5).
    FIRMS gives at most 5 decimals, so a real coordinate is either on an edge or at least
    0.00001 degrees from one (0.0002 in index units at 0.05). Rounding to 6 decimals only
    moves values that are on an edge.
    """
    return math.floor(round(x / grid_deg, SNAP_DECIMALS))


def cell_indices(lat: float, lon: float, grid_deg: float) -> tuple[int, int]:
    return (cell_index(lat, grid_deg), cell_index(lon, grid_deg))


def cell_index_np(values: np.ndarray, grid_deg: float) -> np.ndarray:
    """Same as cell_index, for numpy arrays."""
    return np.floor(np.round(values / grid_deg, SNAP_DECIMALS)).astype(np.int64)


def cell_index_sql(column: str, grid_deg: float) -> str:
    """Same as cell_index, as a DuckDB expression."""
    return f"CAST(FLOOR(ROUND({column} / {grid_deg}, {SNAP_DECIMALS})) AS INTEGER)"


def cell_range(lo: float, hi: float, grid_deg: float) -> tuple[int, int]:
    """First and last cell index whose center lies in [lo, hi).

    Works in index units, so no cell center is ever computed as a float and compared.
    """
    first = math.ceil(round(lo / grid_deg - 0.5, SNAP_DECIMALS))
    last = math.ceil(round(hi / grid_deg - 0.5, SNAP_DECIMALS)) - 1
    return first, last


def tile_id(lat, lon, tile_deg):
    return f"{math.floor(lat / tile_deg)}_{math.floor(lon / tile_deg)}"
