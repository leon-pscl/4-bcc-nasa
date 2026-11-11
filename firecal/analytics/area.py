"""Area selection helpers."""

import math
from dataclasses import dataclass
from typing import Tuple

from firecal.config import Settings


@dataclass
class Area:
    kind: str  # bbox or point
    bbox: Tuple[float, float, float, float] = None  # W,S,E,N
    lat: float = None
    lon: float = None
    radius_km: float = None

    @classmethod
    def from_bbox(cls, w, s, e, n):
        if not (-180 <= w < e <= 180):
            raise ValueError("invalid longitude range")
        if not (-90 <= s < n <= 90):
            raise ValueError("invalid latitude range")
        a = cls(kind="bbox", bbox=(w, s, e, n))
        if a.area_km2() > Settings().MAX_AREA_KM2:
            raise ValueError("area too large")
        return a

    @classmethod
    def from_point(cls, lat, lon, radius_km):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("invalid point")
        if not (1 <= radius_km <= 500):
            raise ValueError("invalid radius")
        a = cls(kind="point", lat=lat, lon=lon, radius_km=radius_km)
        if a.area_km2() > Settings().MAX_AREA_KM2:
            raise ValueError("area too large")
        return a

    def area_km2(self):
        if self.kind == "bbox":
            w, s, e, n = self.bbox
            # sphere area
            R = 6371.0
            lat1, lat2 = math.radians(s), math.radians(n)
            dlon = math.radians(e - w)
            return R * R * (math.sin(lat2) - math.sin(lat1)) * dlon
        # point: circle area
        return math.pi * self.radius_km * self.radius_km

    def contains_cell(self, cell_lat_idx, cell_lon_idx, grid_deg):
        settings = Settings()
        center_lat = (cell_lat_idx + 0.5) * grid_deg
        center_lon = (cell_lon_idx + 0.5) * grid_deg
        if self.kind == "bbox":
            w, s, e, n = self.bbox
            return (w <= center_lon < e) and (s <= center_lat < n)
        # point
        R = 6371.0
        dlat = math.radians(center_lat - self.lat)
        dlon = math.radians(center_lon - self.lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(self.lat))*math.cos(math.radians(center_lat))*math.sin(dlon/2)**2
        dist = 2 * R * math.asin(math.sqrt(a))
        return dist <= self.radius_km