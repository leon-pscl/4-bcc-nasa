"""Cell and tile helpers."""

import math


def cell_indices(lat, lon, grid_deg):
    return (math.floor(lat / grid_deg), math.floor(lon / grid_deg))


def tile_id(lat, lon, tile_deg):
    return f"{math.floor(lat / tile_deg)}_{math.floor(lon / tile_deg)}"