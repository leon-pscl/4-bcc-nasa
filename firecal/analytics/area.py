"""Area selection and validation (Stage 4).

A cell is inside the area if its **center** is inside. West and south edges are
inclusive; east and north are exclusive. Point + radius uses haversine distance
from the cell center.
"""

import math
from dataclasses import dataclass


def haversine_sql(lat1_expr, lon1_expr, lat2, lon2):
    """SQL expression (km) for the great-circle distance between two points."""
    return (
        "6371.0 * 2 * asin(sqrt("
        f"pow(sin(radians(({lat1_expr}) - ({lat2}))/2), 2)"
        f" + cos(radians({lat1_expr})) * cos(radians({lat2}))"
        f" * pow(sin(radians(({lon1_expr}) - ({lon2}))/2), 2)"
        "))"
    )


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
    def from_bbox(cls, w, s, e, n, grid_deg=0.05, max_area_km2=500_000):
        a = cls(w=w, s=s, e=e, n=n, grid_deg=grid_deg)
        a.validate(max_area_km2)
        return a

    @classmethod
    def from_point(cls, lat, lon, radius_km, grid_deg=0.05):
        a = cls(lat=lat, lon=lon, radius_km=radius_km, grid_deg=grid_deg)
        a.validate(float("inf"))
        return a

    def validate(self, max_area_km2):
        if self.radius_km is not None:
            if not (1 <= self.radius_km <= 500):
                raise ValueError("radius must be 1..500 km")
            if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
                raise ValueError("invalid point")
            return
        if not (-180 <= self.w < self.e <= 180):
            raise ValueError("invalid bbox longitude: west must be left of east within -180..180")
        if not (-90 <= self.s < self.n <= 90):
            raise ValueError("invalid bbox latitude")
        if self.area_km2() > max_area_km2:
            raise ValueError(f"area larger than the {max_area_km2} km^2 limit")

    def area_km2(self):
        if self.radius_km is not None:
            return math.pi * self.radius_km * self.radius_km
        R = 6371.0
        to_rad = lambda d: d * math.pi / 180
        return R * R * (math.sin(to_rad(self.n)) - math.sin(to_rad(self.s))) * to_rad(self.e - self.w)

    def cell_bounds(self, cell_lat_idx, cell_lon_idx):
        g = self.grid_deg
        return (cell_lon_idx * g, cell_lat_idx * g, (cell_lon_idx + 1) * g, (cell_lat_idx + 1) * g)

    def cell_inside(self, cell_lat_idx, cell_lon_idx):
        # west and south edges inclusive; east and north exclusive
        g = self.grid_deg
        c_lon = (cell_lon_idx + 0.5) * g
        c_lat = (cell_lat_idx + 0.5) * g
        if self.radius_km is not None:
            R = 6371.0
            dlat = math.radians(c_lat - self.lat)
            dlon = math.radians(c_lon - self.lon)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(self.lat)) * math.cos(
                math.radians(c_lat)) * math.sin(dlon / 2) ** 2
            return 2 * R * math.asin(math.sqrt(a)) <= self.radius_km
        return (self.w <= c_lon < self.e) and (self.s <= c_lat < self.n)

    @staticmethod
    def bbox_sql(area, grid_deg=None):
        """WHERE clause filtering cell centers to the area."""
        g = grid_deg if grid_deg is not None else area.grid_deg
        if area.radius_km is not None:
            g = grid_deg if grid_deg is not None else area.grid_deg
            return (haversine_sql(f"cell_lat_idx*{g}+{g}/2", f"cell_lon_idx*{g}+{g}/2",
                                  area.lat, area.lon)
                    + f" <= {area.radius_km} + 1e-6")
        return f"cell_lon_idx*{g}+{g}/2 >= {area.w} AND cell_lon_idx*{g}+{g}/2 < {area.e} AND cell_lat_idx*{g}+{g}/2 >= {area.s} AND cell_lat_idx*{g}+{g}/2 < {area.n}"
