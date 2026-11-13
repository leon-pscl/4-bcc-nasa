"""Pure planning: which FIRMS chunks to fetch."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Chunk:
    source: str
    bbox: tuple
    date: str
    day_range: int


def _parse(d):
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d))


def _chunks_for_source(source, bbox, seg_start, seg_end, max_days):
    out = []
    cur = seg_start
    while cur <= seg_end:
        dr = min(max_days, (seg_end - cur).days + 1)
        out.append(Chunk(source=source, bbox=tuple(bbox), date=cur.isoformat(), day_range=dr))
        cur = cur + timedelta(days=dr)
    return out


def build_plan(bbox, start, end, availability, settings, manifest=None, today=None):
    start = _parse(start)
    end = _parse(end)
    avail = availability or {}
    max_days = settings.FIRMS_DAY_RANGE_MAX

    chunks = []
    specs = [
        ("MODIS", settings.SERIES_START),
        ("VIIRS", settings.VIIRS_SP_START),
        ("NOAA20", settings.NOAA20_SP_START),
        ("NOAA21", settings.NOAA21_SP_START),
    ]
    for key, min_start in specs:
        sp, nrt = settings.FIRMS_SOURCES[key]
        sp_end = _parse(avail.get(sp, (None, end))[1]) if sp in avail else end
        s = max(start, _parse(min_start))
        sp_seg_end = min(end, sp_end)
        if s <= sp_seg_end:
            chunks += _chunks_for_source(sp, bbox, s, sp_seg_end, max_days)
        nrt_start = max(s, sp_seg_end + timedelta(days=1))
        if nrt_start <= end:
            chunks += _chunks_for_source(nrt, bbox, nrt_start, end, max_days)

    if manifest and today is not None:
        today = _parse(today)
        refresh = settings.NRT_REFRESH_DAYS
        filtered = []
        for c in chunks:
            key = (c.source, tuple(c.bbox), c.date, c.day_range)
            if key not in manifest:
                filtered.append(c)
                continue
            if "NRT" in c.source:
                chunk_end = _parse(c.date) + timedelta(days=c.day_range - 1)
                if (today - chunk_end).days <= refresh:
                    filtered.append(c)
        chunks = filtered
    elif manifest:
        chunks = [c for c in chunks if (c.source, tuple(c.bbox), c.date, c.day_range) not in manifest]

    return chunks