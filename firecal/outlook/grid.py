"""Grid helpers for the 0.15 deg outlook grid.

g_idx = floor(cell_idx / 3) on each axis, where cell_idx is the 0.05 deg index.
Integer arithmetic only; a fine cell's 15 km cell is found by floor division,
identical in Python (// floors toward -inf) and in DuckDB (FLOOR). Coordinates
are never divided by 0.15 to find a cell.
"""

import math
from fractions import Fraction

GRID_DEG = 0.15
FINE_PER_G = 3
_FINE_DEG = 0.05


def g_index(cell_idx):
    """15 km cell index from a 0.05 deg cell index (floor division, -inf)."""
    return cell_idx // FINE_PER_G


def fine_range(g_idx):
    """The fine cell indices of a 15 km cell: (first, last) inclusive."""
    first = g_idx * FINE_PER_G
    return first, first + FINE_PER_G - 1


def g_center(g_idx):
    """Cell center in degrees (display only, never for filtering)."""
    return (g_idx + 0.5) * GRID_DEG


def g_center_sql(alias="g"):
    return f"({alias}.g_lat_idx + 0.5) * {GRID_DEG}"


def g_lat_sql(alias="c"):
    """DuckDB expression: 15 km cell latitude index from fine cell indices."""
    return f"CAST(FLOOR({alias}.cell_lat_idx / 3.0) AS INTEGER)"


def g_lon_sql(alias="c"):
    return f"CAST(FLOOR({alias}.cell_lon_idx / 3.0) AS INTEGER)"


def fine_bounds_sql(g_idx_expr):
    """DuckDB expression for the first fine index of a 15 km cell."""
    return f"({g_idx_expr}) * {FINE_PER_G}"


def _frac(x):
    """Exact rational from a float bbox edge (parses the decimal spelling)."""
    return Fraction(repr(float(x)))


def cell_center_frac(g_idx):
    """Exact rational center of a 15 km cell: (2g+1) * 3/40 degrees."""
    return Fraction(2 * g_idx + 1, 1) * Fraction(3, 40)


def cell_in_box(g_lat_idx, g_lon_idx, w, s, e, n):
    """True iff the 15 km cell's center is in the box.

    West/south edges inclusive, east/north exclusive (same rule as Area).
    Exact rational comparison: no float error at the edges.
    """
    c_lat, c_lon = cell_center_frac(g_lat_idx), cell_center_frac(g_lon_idx)
    return _frac(w) <= c_lon < _frac(e) and _frac(s) <= c_lat < _frac(n)


def g_index_range(w, s, e, n):
    """(g_lat_lo, g_lat_hi, g_lon_lo, g_lon_hi) index ranges covering a box.

    From the fine-cell ranges of the fine grid the box's fine cells span.
    """
    la_lo, la_hi = math.floor(s / _FINE_DEG), math.floor((n - 1e-12) / _FINE_DEG)
    lo_lo, lo_hi = math.floor(w / _FINE_DEG), math.floor((e - 1e-12) / _FINE_DEG)
    return g_index(la_lo), g_index(la_hi), g_index(lo_lo), g_index(lo_hi)


def fine_cells_in_box(g_lat_idx, g_lon_idx, w, s, e, n):
    """Number of this 15 km cell's fine cells whose centers are in the box."""
    count = 0
    f_la0, f_la1 = fine_range(g_lat_idx)
    f_lo0, f_lo1 = fine_range(g_lon_idx)
    for la in range(f_la0, f_la1 + 1):
        c_la = (la + 0.5) * _FINE_DEG
        if not (s <= c_la < n):
            continue
        for lo in range(f_lo0, f_lo1 + 1):
            c_lo = (lo + 0.5) * _FINE_DEG
            if w <= c_lo < e:
                count += 1
    return count


def cell_area_km2(g_lat_idx, g_lon_idx, fine_mask=None, r_km=6371.0):
    """Area of the part of a 15 km cell inside the region box, sphere R = 6371 km.

    fine_mask: optional set of fine (lat_idx, lon_idx) pairs inside the box;
    None means all 9 fine cells (interior cell).
    """
    f_la0, f_la1 = fine_range(g_lat_idx)
    f_lo0, f_lo1 = fine_range(g_lon_idx)
    total = 0.0
    for la in range(f_la0, f_la1 + 1):
        lat1 = math.radians(la * _FINE_DEG)
        lat2 = math.radians((la + 1) * _FINE_DEG)
        dsin = math.sin(lat2) - math.sin(lat1)
        for lo in range(f_lo0, f_lo1 + 1):
            if fine_mask is not None and (la, lo) not in fine_mask:
                continue
            dlon = math.radians(_FINE_DEG)
            total += r_km * r_km * dsin * dlon
    return total
