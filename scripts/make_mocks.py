"""Write frontend/public/mock/api_*.json from the real data via the Flask test client.

The frontend develops against `/mock/api_<name>.json` until the API is deployed.
Every mock is the actual response of the Flask app for **central_kalimantan**
(111°E-116°E, 4°S-1°N) with `synthetic: false` — the real numbers, not placeholders.

Usage:  python scripts/make_mocks.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firecal.config import Settings
from firecal.web import create_app

MOCK_DIR = "frontend/public/mock"


def main():
    settings = Settings.from_env()
    app = create_app(settings)
    client = app.test_client()
    bbox = "110.7,-3.6,115.9,0.8"
    # latest data date comes from coverage.json (written by the pipeline)
    cov = json.load(open(os.path.join(settings.DATA_PROCESSED, "coverage.json")))
    latest = max(r.get("latest_date", "2003-01-01") for r in cov)
    q = f"bbox={bbox}&start=2003-01-01&end={latest}"

    def dump(name, resp):
        os.makedirs(MOCK_DIR, exist_ok=True)
        data = resp.get_json()
        with open(os.path.join(MOCK_DIR, name), "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print("wrote", name)

    endpoints = [
        ("api_calendar.json", f"/api/calendar?{q}"),
        ("api_summary.json", f"/api/summary?{q}"),
        ("api_map.json", f"/api/map?{q}"),
        ("api_hotspots.json", f"/api/hotspots?{q}&page=1&page_size=100&all_sensors=1"),
        ("api_coverage.json", "/api/coverage"),
        ("api_methods.json", "/api/methods?region=southeast_asia"),
        ("api_series.json", f"/api/series?{q}"),
    ]
    # cover variants: forest, farmland, other (same bbox, same range)
    for cover in ("forest", "farmland", "other"):
        endpoints += [
            (f"api_calendar_{cover}.json", f"/api/calendar?{q}&cover={cover}"),
            (f"api_summary_{cover}.json", f"/api/summary?{q}&cover={cover}"),
            (f"api_map_{cover}.json", f"/api/map?{q}&cover={cover}"),
            (f"api_hotspots_{cover}.json", f"/api/hotspots?{q}&page=1&page_size=100&all_sensors=1&cover={cover}"),
            (f"api_series_{cover}.json", f"/api/series?{q}&cover={cover}"),
        ]
    for name, url in endpoints:
        resp = client.get(url)
        assert resp.status_code == 200, (name, resp.status_code, resp.get_data(as_text=True)[:300])
        dump(name, resp)

    # error responses from the real app, so the frontend can develop against them
    def dump_error(name, url, expected_status):
        resp = client.get(url)
        assert resp.status_code == expected_status, (name, resp.status_code,
                                                     resp.get_data(as_text=True)[:300])
        with open(os.path.join(MOCK_DIR, name), "w") as f:
            json.dump(resp.get_json(), f, separators=(",", ":"))
        print("wrote", name)

    dump_error("api_error400.json", "/api/map?bbox=110.7,-3.6,115.9,0.8&start=2012-01-01&end=2018-12-31&month=13", 400)
    dump_error("api_error422.json", "/api/calendar?bbox=95,-45,99,-42&start=2003-01-01&end=2018-12-31", 422)


if __name__ == "__main__":
    main()
