from firecal.fetch.client import FirmsClient, FirmsError


def test_invalid_body_raises():
    def transport(url, timeout=None):
        class R:
            status_code = 200
            text = "error: bad key"
        return R()
    c = FirmsClient("SECRETKEY", transport=transport)
    try:
        c.area_csv("MODIS_SP", (0, 0, 1, 1), 5, "2024-01-01")
    except FirmsError as e:
        assert "SECRETKEY" not in str(e)
    else:
        raise AssertionError("expected FirmsError")


def test_header_only_accepted():
    def transport(url, timeout=None):
        class R:
            status_code = 200
            text = "latitude,longitude,acq_date,acq_time\n"
        return R()
    c = FirmsClient("SECRETKEY", transport=transport)
    body = c.area_csv("MODIS_SP", (0, 0, 1, 1), 5, "2024-01-01")
    assert body.startswith("latitude")


def test_504_retry_succeeds():
    calls = {"n": 0}

    def transport(url, timeout=None):
        calls["n"] += 1
        class R:
            status_code = 504 if calls["n"] == 1 else 200
            text = "latitude,longitude,acq_date,acq_time\n" if calls["n"] > 1 else "gateway timeout"
        return R()
    c = FirmsClient("SECRETKEY", transport=transport)
    # avoid sleeping
    c._backoff = lambda a: 0
    body = c.area_csv("MODIS_SP", (0, 0, 1, 1), 5, "2024-01-01")
    assert "latitude" in body


def test_invalid_key_not_retried():
    calls = {"n": 0}

    def transport(url, timeout=None):
        calls["n"] += 1
        class R:
            status_code = 200
            text = "Invalid API key"
        return R()
    c = FirmsClient("SECRETKEY", transport=transport)
    c._backoff = lambda a: 0
    try:
        c.area_csv("MODIS_SP", (0, 0, 1, 1), 5, "2024-01-01")
    except FirmsError:
        pass
    assert calls["n"] == 1