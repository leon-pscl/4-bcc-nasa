from datetime import date

from firecal.config import Settings
from firecal.fetch.plan import build_plan


def test_plan_chunks_cover_and_no_overlap():
    settings = Settings()
    avail = [
        {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2026-08-31"},
        {"data_id": "MODIS_NRT", "min_date": "2026-09-01", "max_date": "2026-11-11"},
        {"data_id": "VIIRS_SNPP_SP", "min_date": "2012-01-20", "max_date": "2026-07-31"},
        {"data_id": "VIIRS_SNPP_NRT", "min_date": "2026-08-01", "max_date": "2026-11-02"},
    ]
    bbox = (121.116028, 14.583583, 121.643372, 15.445738)
    plan = build_plan(bbox, "2024-01-01", "2024-01-31", avail, settings)
    assert all(c.day_range <= 10 for c in plan)
    # VIIRS starts on 2012-01-20, so present
    viirs = [c for c in plan if c.source.startswith("VIIRS")]
    assert viirs
    # no NRT for 2024
    assert not any(c.source.endswith("NRT") for c in plan)


def test_plan_nrt_starts_after_sp():
    settings = Settings()
    avail = [
        {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2026-06-30"},
        {"data_id": "MODIS_NRT", "min_date": "2026-07-01", "max_date": "2026-11-11"},
        {"data_id": "VIIRS_SNPP_SP", "min_date": "2012-01-20", "max_date": "2026-06-30"},
        {"data_id": "VIIRS_SNPP_NRT", "min_date": "2026-07-01", "max_date": "2026-11-02"},
    ]
    bbox = (-64, -18, -60, -14)
    plan = build_plan(bbox, "2003-01-01", "2026-11-10", avail, settings)
    nrt = [c for c in plan if c.source.endswith("NRT")]
    assert nrt
    assert all(c.date >= "2026-07-01" for c in nrt)