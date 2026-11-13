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
    viirs_start_min = _parse(settings.VIIRS_SP_START)

    chunks = []

    # MODIS
    modis_sp, modis_nrt = settings.FIRMS_SOURCES["MODIS"]
    sp_end_modis = _parse(avail.get(modis_sp, (None, end))[1]) if modis_sp in avail else end
    # segment 1: SP up to sp_end
    s = max(start, date(2003, 1, 1))
    sp_seg_end = min(end, sp_end_modis)
    if s <= sp_seg_end:
        chunks += _chunks_for_source(modis_sp, bbox, s, sp_seg_end, max_days)
    # segment 2: NRT after
    nrt_start = max(s, sp_seg_end + timedelta(days=1))
    if nrt_start <= end:
        chunks += _chunks_for_source(modis_nrt, bbox, nrt_start, end, max_days)

    # VIIRS
    viirs_sp, viirs_nrt = settings.FIRMS_SOURCES["VIIRS"]
    sp_end_viirs = _parse(avail.get(viirs_sp, (None, end))[1]) if viirs_sp in avail else end
    s = max(start, viirs_start_min)
    sp_seg_end = min(end, sp_end_viirs)
    if s <= sp_seg_end:
        chunks += _chunks_for_source(viirs_sp, bbox, s, sp_seg_end, max_days)
    nrt_start = max(s, sp_seg_end + timedelta(days=1))
    if nrt_start <= end:
        chunks += _chunks_for_source(viirs_nrt, bbox, nrt_start, end, max_days)

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