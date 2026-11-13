import io

from firecal.config import Settings
from firecal.fetch.client import FirmsClient, FirmsError
from firecal.fetch.plan import build_plan
from firecal.fetch.ratelimit import RateLimiter


def test_client_rejects_non_csv():
    def transport(url, timeout=120):
        class R:
            status_code = 200
            text = "error: bad key"
        return R()
    c = FirmsClient("SECRETKEY", transport=transport)
    try:
        c.area_csv("MODIS_SP", (-64, -18, -60, -14), 5, "2024-01-01")
    except FirmsError as e:
        assert "SECRETKEY" not in str(e)
    else:
        raise AssertionError("expected FirmsError")


def test_client_accepts_header_only():
    def transport(url, timeout=120):
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date\n"
        return R()
    c = FirmsClient("KEY", transport=transport)
    out = c.area_csv("MODIS_SP", (-64, -18, -60, -14), 5, "2024-01-01")
    assert "latitude" in out


def test_client_retries_504():
    calls = {"n": 0}
    def transport(url, timeout=120):
        if "area/csv" in url:
            calls["n"] += 1
        class R:
            status_code = 200 if calls["n"] > 1 else 504
            text = "latitude,longitude,acq_date\n" if calls["n"] > 1 else "gateway timeout"
        return R()
    c = FirmsClient("KEY", transport=transport, retries=2, backoff_base=0)
    out = c.area_csv("MODIS_SP", (-64, -18, -60, -14), 5, "2024-01-01")
    assert calls["n"] == 2


def test_client_does_not_retry_invalid_key():
    calls = {"n": 0}
    def transport(url, timeout=120):
        if "area/csv" in url:
            calls["n"] += 1
        class R:
            status_code = 200
            text = "Invalid MAP_KEY"
        return R()
    c = FirmsClient("KEY", transport=transport, retries=3, backoff_base=0)
    try:
        c.area_csv("MODIS_SP", (-64, -18, -60, -14), 5, "2024-01-01")
    except FirmsError:
        pass
    assert calls["n"] == 1


def test_plan_basics():
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    chunks = build_plan((-64, -18, -60, -14), "2003-01-01", "2026-07-10", avail, settings)
    assert all(c.day_range <= 10 for c in chunks)
    # VIIRS starts on 2012-01-20
    viirs_chunks = [c for c in chunks if "VIIRS" in c.source]
    assert viirs_chunks
    assert min(c.date for c in viirs_chunks) == "2012-01-20"
    # NRT appears after SP end
    nrt = [c for c in chunks if c.source.endswith("NRT")]
    assert nrt


def test_ratelimit_waits():
    clock = {"t": 0.0}
    slept = {"n": 0}
    def clk():
        return clock["t"]
    def slp(s):
        slept["n"] += 1
        clock["t"] += s
    rl = RateLimiter(budget=20, window=600, clock=clk, sleeper=slp)
    rl.acquire(10)
    rl.acquire(10)
    rl.acquire(10)  # should wait
    assert slept["n"] >= 1


def test_plan_exact_coverage():
    import datetime
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    chunks = build_plan((-64, -18, -60, -14), "2003-01-01", "2026-07-10", avail, settings, today="2026-07-10")
    for src in set(c.source for c in chunks):
        src_chunks = [c for c in chunks if c.source == src]
        covered = set()
        for c in src_chunks:
            d = datetime.date.fromisoformat(c.date)
            for i in range(c.day_range):
                covered.add(d + datetime.timedelta(days=i))
        # no overlaps
        assert sum(c.day_range for c in src_chunks) == len(covered)
        # exact expected dates per source segment
        if src == "MODIS_SP":
            expected = set(datetime.date(2003, 1, 1) + datetime.timedelta(days=i)
                           for i in range((datetime.date(2026, 6, 30) - datetime.date(2003, 1, 1)).days + 1))
            assert covered == expected
        if src == "MODIS_NRT":
            expected = set(datetime.date(2026, 7, 1) + datetime.timedelta(days=i)
                           for i in range((datetime.date(2026, 7, 10) - datetime.date(2026, 7, 1)).days + 1))
            assert covered == expected


def test_plan_nrt_start():
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    chunks = build_plan((-64, -18, -60, -14), "2026-06-25", "2026-07-10", avail, settings, today="2026-07-10")
    nrt = [c for c in chunks if c.source.endswith("NRT")]
    assert nrt
    assert any(c.date == "2026-07-01" for c in nrt)


def test_resume(tmp_path):
    calls = {"n": 0}
    def transport(url, timeout=120):
        if "area/csv" in url:
            calls["n"] += 1
        if "data_availability" in url:
            class R:
                status_code = 200
                text = "data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
            return R()
        if calls["n"] == 3:
            raise TimeoutError("boom")
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date\n"
        return R()
    from firecal.fetch.cli import cmd_backfill
    import argparse
    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.FIRMS_MAP_KEY = "KEY"
    settings.FIRMS_DAY_RANGE_MAX = 2
    client = FirmsClient("KEY", settings.FIRMS_BASE_URL, transport=transport, retries=0, backoff_base=0)
    ns = argparse.Namespace(region=None, bbox="121.1,14.5,121.6,15.4", name="x",
                            start="2024-01-01", end="2024-01-04", dry_run=False)
    try:
        cmd_backfill(ns, settings, client=client)
    except SystemExit:
        pass
    # second run: should fetch remaining (fewer requests)
    calls2 = {"n": calls["n"]}
    def transport2(url, timeout=120):
        if "area/csv" in url:
            calls2["n"] += 1
        if "data_availability" in url:
            class R:
                status_code = 200
                text = "data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
            return R()
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date\n"
        return R()
    client2 = FirmsClient("KEY", settings.FIRMS_BASE_URL, transport=transport2, retries=0, backoff_base=0)
    cmd_backfill(ns, settings, client=client2)
    # third run: zero requests
    calls3 = {"n": 0}
    def transport3(url, timeout=120):
        if "area/csv" in url:
            calls3["n"] += 1
        if "data_availability" in url:
            class R:
                status_code = 200
                text = "data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
            return R()
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date\n"
        return R()
    client3 = FirmsClient("KEY", settings.FIRMS_BASE_URL, transport=transport3, retries=0, backoff_base=0)
    cmd_backfill(ns, settings, client=client3)
    assert calls3["n"] == 0


def test_dry_run_no_requests(tmp_path):
    calls = {"n": 0}
    def transport(url, timeout=120):
        if "area/csv" in url:
            calls["n"] += 1
        if "data_availability" in url:
            class R:
                status_code = 200
                text = "data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
            return R()
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date\n"
        return R()
    from firecal.fetch.cli import cmd_backfill
    import argparse
    settings = Settings()
    settings.DATA_RAW = str(tmp_path / "raw")
    settings.FIRMS_MAP_KEY = "KEY"
    client = FirmsClient("KEY", settings.FIRMS_BASE_URL, transport=transport, retries=0, backoff_base=0)
    ns = argparse.Namespace(region=None, bbox="121.1,14.5,121.6,15.4", name="x",
                            start="2024-01-01", end="2024-01-04", dry_run=True)
    cmd_backfill(ns, settings, client=client)
    assert calls["n"] == 0


def test_key_absent_from_traceback():
    def transport(url, timeout=120):
        raise TimeoutError("network down")
    c = FirmsClient("SECRETKEY", transport=transport, retries=0)
    try:
        c.area_csv("MODIS_SP", (0, 0, 1, 1), 1, "2024-01-01")
    except FirmsError as e:
        import traceback
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        assert "SECRETKEY" not in tb


def test_nrt_refresh_replans_recent_not_old():
    import datetime
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    manifest = {("MODIS_NRT", (-64.0, -18.0, -60.0, -14.0), "2026-07-01", 5)}
    # recent chunk within refresh
    chunks = build_plan((-64, -18, -60, -14), "2026-06-25", "2026-07-10", avail, settings,
                       manifest=manifest, today="2026-07-03")
    assert any(c.source == "MODIS_NRT" and c.date == "2026-07-01" for c in chunks)
    # old chunk not refreshed
    old_manifest = {("MODIS_NRT", (-64.0, -18.0, -60.0, -14.0), "2025-01-01", 5)}
    chunks2 = build_plan((-64, -18, -60, -14), "2024-01-01", "2025-01-10", avail, settings,
                        manifest=old_manifest, today="2026-07-03")
    assert not any(c.source == "MODIS_NRT" and c.date == "2025-01-01" for c in chunks2)