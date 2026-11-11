"""Pure planning of FIRMS fetch chunks."""

from collections import namedtuple
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

Chunk = namedtuple("Chunk", ["source", "bbox", "date", "day_range"])


def _parse_date(v) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v), "%Y-%m-%d").date()


def _availability_map(availability) -> Dict[str, Tuple[date, date]]:
    out: Dict[str, Tuple[date, date]] = {}
    if isinstance(availability, dict):
        for k, v in availability.items():
            if isinstance(v, (tuple, list)):
                out[k] = (_parse_date(v[0]), _parse_date(v[1]))
            elif isinstance(v, dict):
                s = v.get("start") or v.get("start_date")
                e = v.get("end") or v.get("end_date")
                out[k] = (_parse_date(s), _parse_date(e))
        return out
    for row in availability or []:
        src = (row.get("data_id") or row.get("source")) if isinstance(row, dict) else row[0]
        s = (row.get("min_date") or row.get("start_date") or row.get("start")) if isinstance(row, dict) else row[1]
        e = (row.get("max_date") or row.get("end_date") or row.get("end")) if isinstance(row, dict) else row[2]
        out[src] = (_parse_date(s), _parse_date(e))
    return out


def build_plan(bbox, start, end, availability, settings) -> List[Chunk]:
    avail = _availability_map(availability)
    start_d = _parse_date(start)
    end_d = _parse_date(end)
    max_dr = settings.FIRMS_DAY_RANGE_MAX
    viirs_start = _parse_date(settings.VIIRS_SP_START)

    chunks: List[Chunk] = []

    # sensor -> (sp source, nrt source)
    sensors = [("MODIS", settings.FIRMS_SOURCES["MODIS"]),
               ("VIIRS", settings.FIRMS_SOURCES["VIIRS"])]

    for sensor, srcs in sensors:
        sp_src = srcs["SP"]
        nrt_src = srcs["NRT"]
        sp_avail = avail.get(sp_src)
        nrt_avail = avail.get(nrt_src)

        # SP segment
        sp_start = start_d
        if sensor == "VIIRS":
            sp_start = max(sp_start, viirs_start)
        sp_end = end_d
        if sp_avail:
            sp_start = max(sp_start, sp_avail[0])
            sp_end = min(sp_end, sp_avail[1])
        if sp_start <= sp_end:
            # chunk from sp_start to sp_end
            d = sp_start
            while d <= sp_end:
                dr = min(max_dr, (sp_end - d).days + 1)
                chunks.append(Chunk(sp_src, tuple(bbox), d.isoformat(), dr))
                d = d + timedelta(days=dr)

        # NRT segment starts after SP end
        nrt_start = start_d
        if sp_avail and sp_avail[1] >= sp_start:
            nrt_start = max(nrt_start, sp_avail[1] + timedelta(days=1))
        if sensor == "VIIRS":
            nrt_start = max(nrt_start, viirs_start)
        nrt_end = end_d
        if nrt_avail:
            nrt_start = max(nrt_start, nrt_avail[0])
            nrt_end = min(nrt_end, nrt_avail[1])
        if nrt_start <= nrt_end:
            d = nrt_start
            while d <= nrt_end:
                dr = min(max_dr, (nrt_end - d).days + 1)
                chunks.append(Chunk(nrt_src, tuple(bbox), d.isoformat(), dr))
                d = d + timedelta(days=dr)

    return chunks