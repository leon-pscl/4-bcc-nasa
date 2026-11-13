"""FIRMS API client (download only)."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class FirmsError(Exception):
    pass


def _mask(text: str, key: str) -> str:
    if key:
        return text.replace(key, "***")
    return text


class FirmsClient:
    def __init__(self, map_key, base_url="https://firms.modaps.eosdis.nasa.gov",
                 transport=requests.get, timeout=120, retries=5, backoff_base=5,
                 sleeper=time.sleep):
        self.map_key = map_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.backoff_base = backoff_base
        self.sleeper = sleeper

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}".replace(self.map_key, "***")

    def _request(self, path: str, validate_csv: bool = True) -> str:
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.transport(url, timeout=self.timeout)
            except Exception as exc:  # network/timeout
                last_exc = exc
                if attempt < self.retries:
                    self.sleeper(self.backoff_base * (2 ** attempt))
                    continue
                raise FirmsError(_mask(str(exc), self.map_key)) from None
            status = getattr(resp, "status_code", 200)
            text = getattr(resp, "text", "")
            if status >= 400 and status < 500:
                raise FirmsError(_mask(text[:200], self.map_key)) from None
            if status >= 500:
                last_exc = FirmsError(_mask(text[:200], self.map_key))
                if attempt < self.retries:
                    self.sleeper(self.backoff_base * (2 ** attempt))
                    continue
                raise last_exc from None
            if validate_csv:
                first_line = text.splitlines()[0] if text.splitlines() else ""
                if "latitude" not in first_line or "acq_date" not in first_line:
                    raise FirmsError(_mask(text[:200], self.map_key)) from None
            return text
        raise FirmsError(_mask(str(last_exc), self.map_key)) from None

    def area_csv(self, source, bbox, day_range, date=None):
        w, s, e, n = bbox
        path = f"/api/area/csv/{self.map_key}/{source}/{w},{s},{e},{n}/{day_range}"
        if date is not None:
            path += f"/{date}"
        return self._request(path)

    def data_availability(self, source="all"):
        path = f"/api/data_availability/csv/{self.map_key}/{source}"
        return self._request(path, validate_csv=False)

    def key_status(self):
        path = f"/api/map_key_status/{self.map_key}"
        return self._request(path, validate_csv=False)