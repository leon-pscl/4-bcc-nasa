"""Every frontend mock (frontend/public/mock/api_*.json) must satisfy the same
shape the frontend's zod schemas (frontend/src/api/schemas.ts) require."""

import json
import os

import pytest

MOCK_DIR = os.path.join("frontend", "public", "mock")
FILES = ["api_calendar.json", "api_summary.json", "api_map.json", "api_hotspots.json",
         "api_coverage.json", "api_methods.json", "api_error400.json", "api_error422.json",
         "api_series.json"]


def _load(name):
    with open(os.path.join(MOCK_DIR, name)) as f:
        return json.load(f)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_calendar(d):
    assert _is_num(d["query"]["start"] is not None and True) or isinstance(d["query"]["start"], str)
    assert isinstance(d["unit"], str)
    years = d["years"]
    assert isinstance(years, list) and years and all(isinstance(y, int) for y in years)
    values = d["values"]
    assert len(values) == len(years)
    for row in values:
        assert len(row) == 12
        assert all(v is None or _is_num(v) for v in row)
    partial = d["partial"]
    if partial is not None:
        assert all(isinstance(partial[k], int) for k in ("year", "month", "through_day"))
    for key in ("monthly_median", "monthly_p25", "monthly_p75"):
        assert len(d[key]) == 12 and all(_is_num(v) for v in d[key])
    for key in ("anomaly", "anomaly_pct"):
        assert len(d[key]) == len(years)
        for row in d[key]:
            assert len(row) == 12
            assert all(v is None or _is_num(v) for v in row)
    assert len(d["annual_totals"]) == len(years) and all(_is_num(v) for v in d["annual_totals"])
    assert all(isinstance(y, int) for y in d["partial_years"])
    assert all(isinstance(y, int) for y in d["baseline_years"])
    assert d["baseline_warning"] is None or isinstance(d["baseline_warning"], str)
    assert d["coverage_warning"] is None or isinstance(d["coverage_warning"], str)
    assert isinstance(d["synthetic"], bool)
    assert isinstance(d["data_version"], str) and d["data_version"]
    q = d["query"]
    if "bbox" in q:
        assert len(q["bbox"]) == 4 and all(_is_num(v) for v in q["bbox"])
    else:
        assert len(q["point"]) == 2 and _is_num(q["radius_km"])


def _check_summary(d):
    assert _is_num(d["total"])
    for key in ("peak_month", "peak_year"):
        assert d[key] is None or isinstance(d[key], dict)
    cur = d["current_month"]
    if cur is not None:
        assert all(_is_num(cur[k]) for k in
                   ("year", "month", "through_day", "value", "median_same_span", "pct_vs_median",
                    "forest_share", "median_forest_share"))
    assert isinstance(d["latest_data_date"], str) and len(d["latest_data_date"]) == 10
    assert isinstance(d["synthetic"], bool)
    assert isinstance(d["data_version"], str) and d["data_version"]


def _check_series(d):
    months = d["months"]
    assert isinstance(months, list) and months and all(isinstance(m, str) and len(m) == 7 for m in months)
    for key in ("aqua", "snpp", "noaa20", "noaa21", "aqua_k", "harmonized"):
        assert len(d[key]) == len(months)
        assert all(_is_num(v) for v in d[key])
    assert isinstance(d["switch_date"], str)
    assert isinstance(d["outage_days"], list)
    val = d["validation"]
    assert all(isinstance(y, int) for y in val["overlap_years"])
    assert all(isinstance(y, int) for y in val["fit_years"])
    assert _is_num(val["pearson_r"]) and _is_num(val["bias_pct"])
    assert val["typical_year_error_pct"] is None or _is_num(val["typical_year_error_pct"])
    assert isinstance(val["held_out_months"], int) and isinstance(val["in_sample_months"], int)
    assert isinstance(val["per_year"], dict) and isinstance(val["in_sample"], dict)


def _check_map(d):
    assert _is_num(d["grid_deg"])
    assert d["aggregated_to"] is None or _is_num(d["aggregated_to"])
    for c in d["cells"]:
        assert _is_num(c["lat"]) and _is_num(c["lon"]) and _is_num(c["value"])
    assert isinstance(d["data_version"], str) and d["data_version"]


def _check_hotspots(d):
    assert isinstance(d["page"], int) and isinstance(d["page_size"], int) and isinstance(d["total"], int)
    assert len(d["rows"]) <= d["page_size"]
    for r in d["rows"]:
        assert isinstance(r["date_local"], str) and len(r["date_local"]) == 10
        assert isinstance(r["acq_datetime_utc"], str) and r["acq_datetime_utc"]
        assert _is_num(r["latitude"]) and _is_num(r["longitude"])
        assert isinstance(r["confidence_class"], str)
        assert _is_num(r["frp"])
        assert isinstance(r["daynight"], str)
        for k in ("sensor", "platform", "processing"):
            assert k not in r or isinstance(r[k], str)
    assert isinstance(d["data_version"], str) and d["data_version"]


def _check_coverage(d):
    for r in d["regions"]:
        assert isinstance(r["name"], str) and isinstance(r["label"], str)
        assert len(r["bbox"]) == 4 and all(_is_num(v) for v in r["bbox"])
        assert isinstance(r["countries"], list) and all(isinstance(c, str) for c in r["countries"])
        assert isinstance(r["start"], str) and isinstance(r["end"], str) and isinstance(r["latest_date"], str)
        assert isinstance(r["platforms"], list)
        assert isinstance(r["synthetic"], bool)
    for s in d["starter_areas"]:
        assert isinstance(s["name"], str) and isinstance(s["label"], str) and isinstance(s["region"], str)
        assert len(s["bbox"]) == 4 and all(_is_num(v) for v in s["bbox"])
    assert isinstance(d["data_version"], str) and d["data_version"]


def _check_methods(d):
    assert isinstance(d["region"], str)
    cal = d["calibration"]
    assert _is_num(cal["k_median"]) and _is_num(cal["k_min"]) and _is_num(cal["k_max"])
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in cal["count_per_level"].items())
    for key in ("calibration_years", "validation_years"):
        block = d["validation"][key]
        assert all(isinstance(y, int) for y in block["years"])
        m = block["metrics"]
        assert _is_num(m["pearson_r"]) and _is_num(m["bias_pct"]) and _is_num(m["median_abs_pct_error"])
        assert isinstance(m["monthly_viirs"], list) and m["monthly_viirs"]
        assert isinstance(m["monthly_modis"], list) and m["monthly_modis"]
        assert all(_is_num(v) for v in m["monthly_viirs"])
        assert all(_is_num(v) for v in m["monthly_modis"])
    assert isinstance(d["data_version"], str) and d["data_version"]


def _check_error(d, expect_field):
    assert isinstance(d["error"], str) and d["error"]
    if expect_field:
        assert isinstance(d.get("field"), str) and d["field"]


CHECKS = {
    "api_calendar.json": _check_calendar,
    "api_summary.json": _check_summary,
    "api_map.json": _check_map,
    "api_hotspots.json": _check_hotspots,
    "api_coverage.json": _check_coverage,
    "api_methods.json": _check_methods,
    "api_series.json": _check_series,
}


@pytest.mark.parametrize("name", FILES)
def test_mock_matches_frontend_contract(name):
    d = _load(name)
    if name == "api_error400.json":
        _check_error(d, expect_field=True)
    elif name == "api_error422.json":
        _check_error(d, expect_field=False)
        assert isinstance(d.get("covered_regions"), list)
    else:
        CHECKS[name](d)


def test_all_mock_files_present():
    for name in FILES:
        assert os.path.exists(os.path.join(MOCK_DIR, name)), name
