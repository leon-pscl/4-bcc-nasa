import json, os, tempfile

from firecal.regions import load_regions, regions_dict, starter_areas_dict


def test_regions_load():
    regions, starters = load_regions()
    assert len(regions) == 2
    assert "southeast_asia" in regions_dict()


def test_regions_no_overlap():
    # broken file with overlapping regions
    data = {"regions": [
        {"name": "a", "label": "A", "bbox": [0, 0, 10, 10], "countries": [], "history": "country_files"},
        {"name": "b", "label": "B", "bbox": [5, 5, 15, 15], "countries": [], "history": "country_files"},
    ], "starter_areas": []}
    d = tempfile.mkdtemp()
    p = os.path.join(d, "regions.json")
    json.dump(data, open(p, "w"))
    try:
        load_regions(p)
    except ValueError as e:
        assert "overlap" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_starter_area_oversized():
    data = {"regions": [
        {"name": "r", "label": "R", "bbox": [0, 0, 100, 100], "countries": [], "history": "country_files"},
    ], "starter_areas": [
        {"name": "s", "label": "S", "region": "r", "bbox": [0, 0, 90, 90]},
    ]}
    d = tempfile.mkdtemp()
    p = os.path.join(d, "regions.json")
    json.dump(data, open(p, "w"))
    try:
        load_regions(p)
    except ValueError as e:
        assert "too large" in str(e) or "oversized" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_starter_area_outside_region():
    data = {"regions": [
        {"name": "r", "label": "R", "bbox": [0, 0, 10, 10], "countries": [], "history": "country_files"},
    ], "starter_areas": [
        {"name": "s", "label": "S", "region": "r", "bbox": [20, 20, 21, 21]},
    ]}
    import tempfile, json, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "regions.json")
    json.dump(data, open(p, "w"))
    try:
        from firecal.regions import load_regions
        load_regions(p)
    except ValueError as e:
        assert "outside region" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_unknown_region_starter():
    data = {"regions": [
        {"name": "r", "label": "R", "bbox": [0, 0, 10, 10], "countries": [], "history": "country_files"},
    ], "starter_areas": [
        {"name": "s", "label": "S", "region": "nope", "bbox": [0, 0, 1, 1]},
    ]}
    d = tempfile.mkdtemp()
    p = os.path.join(d, "regions.json")
    json.dump(data, open(p, "w"))
    try:
        load_regions(p)
    except ValueError as e:
        assert "unknown region" in str(e)
    else:
        raise AssertionError("expected ValueError")