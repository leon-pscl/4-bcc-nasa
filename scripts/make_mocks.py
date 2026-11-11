"""Generate mock API responses from synthetic dataset."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATA_PROCESSED", "data/synthetic/processed")

from firecal.web import create_app

app = create_app()
client = app.test_client()
out = Path("frontend/public/mock")
out.mkdir(parents=True, exist_ok=True)
endpoints = ["/api/coverage", "/api/calendar?bbox=-64,-18,-60,-14&start=2003-01-01&end=2024-01-31",
             "/api/summary?bbox=-64,-18,-60,-14&start=2003-01-01&end=2024-01-31",
             "/api/map?bbox=-64,-18,-60,-14&start=2003-01-01&end=2024-01-31",
             "/api/methods"]
for ep in endpoints:
    r = client.get(ep)
    name = ep.split("?")[0].strip("/").replace("/", "_") + ".json"
    (out / name).write_text(r.get_data(as_text=True))
print("mocks written to", out)