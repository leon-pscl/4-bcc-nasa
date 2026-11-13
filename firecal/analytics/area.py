"""Area selection and validation."""

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class Area:
    w: float = None
    s: float = None
    e: float = None
    n: float = None
    lat: float = None
    lon: float = None
    radius_km: float = None
    grid_deg: float = 0.05

    @classmethod
    def from_bbox(cls, w, s, e, n, grid_deg=0.05):
        a = cls(w=w, s=s, e=e, n=n, grid_deg=grid_deg)
        a.validate()
        return a

    @classmethod
    def from_point(cls, lat, lon, radius_km, grid_deg=0.05):
        a = cls(lat=lat, lon=lon, radius_km=radius_km, grid_deg=grid_deg)
        a.validate()
        return a

    def validate(self):
        if self.radius_km is None:
            if not (-180 <= self.w < self.e <= 180):
                raise ValueError("invalid bbox longitude")
            if not (-90 <= self.s < self.n <= 90):
                raise ValueError("invalid bbox latitude")
        else:
            if not (1 <= self.radius_km <= 500):
                raise ValueError("radius must be 1..500 km")

    def area_km2(self):
        if self.radius_km is None:
            R = 6371.0
            to_rad = lambda d: d * math.pi / 180
            return R * R * (math.sin(to_rad(self.n)) - math.sin(to_rad(self.s))) * to_rad(self.e - self.w)
        return math.pi * self.radius_km * self.radius_km

    def contains_cell(self, cell_lat_idx, cell_lon_idx):
        g = self.grid_deg
        clat = (cell_lat_idx + 0.5) * g
        clon = (cell_lon_idx + 0.5) * g
        if self.radius_km is None:
            return self.w <= clon < self.e and self.s <= clat < self.n
        # haversine
        R = 6371.0
        dlat = math.radians(clat - self.lat)
        dlon = math.radians(clon - self.lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(self.lat))*math.cos(math.radians(clat))*math.sin(dlon/2)**2
        dist = 2 * R * math.asin(math.sqrt(a))
        return dist <= self.radius_km