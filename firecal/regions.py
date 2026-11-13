"""Load and validate config/regions.json."""

import json
import os

from firecal.config import Settings


def _path():
    return os.path.join("config", "regions.json")


def load_regions(path=None):
    path = path or _path()
    with open(path) as f:
        data = json.load(f)
    regions = data["regions"]
    starters = data["starter_areas"]
    # validate no overlap
    def bbox_overlap(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            if bbox_overlap(regions[i]["bbox"], regions[j]["bbox"]):
                raise ValueError(f"regions overlap: {regions[i]['name']} and {regions[j]['name']}")
    region_names = {r["name"] for r in regions}
    max_area = Settings().MAX_AREA_KM2
    for sa in starters:
        if sa["region"] not in region_names:
            raise ValueError(f"unknown region for starter area: {sa['name']}")
        # area check
        from firecal.analytics.area import Area
        a = Area.from_bbox(*sa["bbox"])
        if a.area_km2() > max_area:
            raise ValueError(f"starter area too large: {sa['name']}")
        # inside region
        r = next(x for x in regions if x["name"] == sa["region"])
        rb = r["bbox"]
        if not (rb[0] <= sa["bbox"][0] and sa["bbox"][2] <= rb[2] and rb[1] <= sa["bbox"][1] and sa["bbox"][3] <= rb[3]):
            raise ValueError(f"starter area outside region: {sa['name']}")
    return regions, starters


def regions_dict(path=None):
    regions, _ = load_regions(path)
    return {r["name"]: tuple(r["bbox"]) for r in regions}


def starter_areas_dict(path=None):
    _, starters = load_regions(path)
    return {s["name"]: tuple(s["bbox"]) for s in starters}