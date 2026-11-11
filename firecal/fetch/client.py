"""FIRMS HTTP client. Only downloads; never parses beyond the header check."""

import time
from typing import Callable, List, Optional

import requests


class FirmsError(Exception):
    pass


class FirmsClient:
    def __init__(
        self,
        map_key: str,
        base_url: str = "https://firms.modaps.eosdis.nasa.gov",
        transport: Callable = requests.get,
        timeout: int = 120,
    ):
        self.map_key = map_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def _safe(self, text: str) -> str:
        return text.replace(self.map_key, "***") if self.map_key else text

    def _fetch(self, url: str, require_fire: bool = True) -> str:
        last_exc = None
        for attempt in range(self._retries()):
            try:
                resp = self.transport(url, timeout=self.timeout)
            except Exception as exc:  # network / timeout
                last_exc = exc
                time.sleep(self._backoff(attempt))
                continue
            status = getattr(resp, "status_code", 200)
            body = getattr(resp, "text", None)
            if body is None:
                body = getattr(resp, "content", b"").decode("utf-8", "replace")
            if status >= 500:
                last_exc = FirmsError(f"HTTP {status}")
                time.sleep(self._backoff(attempt))
                continue
            if require_fire:
                first = body.splitlines()[0] if body.strip() else ""
                if "latitude" not in first or "acq_date" not in first:
                    raise FirmsError(self._safe(body[:200]))
            return body
        if last_exc is not None:
            raise FirmsError(self._safe(str(last_exc)))
        raise FirmsError("request failed")

    def _retries(self):
        try:
            from firecal.config import Settings

            return Settings().FIRMS_RETRIES
        except Exception:
            return 5

    def _backoff(self, attempt: int) -> float:
        return 5 * (2 ** attempt)

    def area_csv(self, source: str, bbox, day_range: int, date: Optional[str] = None) -> str:
        w, s, e, n = bbox
        url = f"{self.base_url}/api/area/csv/{self.map_key}/{source}/{w},{s},{e},{n}/{day_range}"
        if date:
            url += f"/{date}"
        return self._fetch(url)

    def data_availability(self, source: str = "all") -> List[dict]:
        url = f"{self.base_url}/api/data_availability/csv/{self.map_key}/{source}"
        body = self._fetch(url, require_fire=False)
        import csv, io

        rows = list(csv.DictReader(io.StringIO(body)))
        return rows

    def key_status(self) -> dict:
        url = f"{self.base_url}/api/map_key_status/{self.map_key}"
        try:
            resp = self.transport(url, timeout=self.timeout)
            body = getattr(resp, "text", "")
            return {"raw": body[:500]}
        except Exception as exc:
            return {"error": self._safe(str(exc))}