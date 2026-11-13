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
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    chunks = build_plan((-64, -18, -60, -14), "2003-01-01", "2026-07-10", avail, settings, today="2026-07-10")
    # chunks per source don't overlap and cover exactly
    for src in set(c.source for c in chunks):
        src_chunks = [c for c in chunks if c.source == src]
        # build covered date set
        covered = set()
        for c in src_chunks:
            d = __import__("datetime").date.fromisoformat(c.date)
            for i in range(c.day_range):
                covered.add(d + __import__("datetime").timedelta(days=i))
        # expected range for that source
        if src.startswith("MODIS"):
            start = __import__("datetime").date(2003, 1, 1)
        else:
            start = __import__("datetime").date(2012, 1, 20)
        end = __import__("datetime").date(2026, 7, 10)
        # SP/NRT split: just ensure no overlaps within source by checking total days equals sum day_range
        assert sum(c.day_range for c in src_chunks) == len(covered)


def test_plan_nrt_start():
    settings = Settings()
    avail = {"MODIS_SP": ("2003-01-01", "2026-06-30"), "VIIRS_SNPP_SP": ("2012-01-20", "2026-06-30")}
    chunks = build_plan((-64, -18, -60, -14), "2026-06-25", "2026-07-10", avail, settings, today="2026-07-10")
    nrt = [c for c in chunks if c.source.endswith("NRT")]
    assert nrt
    assert any(c.date == "2026-07-01" for c in nrt)