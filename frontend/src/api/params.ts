import type { AppState, AreaState } from '../state/urlState';
import type { CoverageResponse } from './schemas';
import { areaKm2, pointAreaKm2, MAX_AREA_KM2 } from '../lib/geo';

export function buildAreaParams(area: AreaState): URLSearchParams {
  const p = new URLSearchParams();
  if (area.kind === 'bbox') p.set('bbox', area.bbox.join(','));
  else { p.set('point', area.point.join(',')); p.set('radius_km', String(area.radius_km)); }
  return p;
}

export function buildQueryParams(state: Pick<AppState, 'area' | 'start' | 'end'>): string {
  const p = buildAreaParams(state.area);
  p.set('start', state.start);
  p.set('end', state.end);
  return p.toString();
}

export function isAreaValid(area: AreaState, coverage?: CoverageResponse): boolean {
  if (area.kind === 'bbox') {
    const [w, s, e, n] = area.bbox;
    if (![w, s, e, n].every(Number.isFinite)) return false;
    if (n < -90 || n > 90 || s < -90 || s > 90 || e < -180 || e > 180 || w < -180 || w > 180) return false;
    if (s >= n || w >= e) return false;
    if (areaKm2(n, s, e, w) > MAX_AREA_KM2) return false;
    if (!coverage) return true;
    return coverage.regions.some((r) => w >= r.bbox[0] && e <= r.bbox[2] && s >= r.bbox[1] && n <= r.bbox[3]);
  }
  const [lat, lon] = area.point;
  const r = area.radius_km;
  if (![lat, lon, r].every(Number.isFinite)) return false;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return false;
  if (r < 1 || r > 500) return false;
  if (pointAreaKm2(r) > MAX_AREA_KM2) return false;
  if (!coverage) return true;
  return coverage.regions.some((reg) => lon >= reg.bbox[0] && lon <= reg.bbox[2] && lat >= reg.bbox[1] && lat <= reg.bbox[3]);
}

export function isDatesValid(start: string, end: string, coverage?: CoverageResponse, area?: AreaState): boolean {
  if (!start || !end || start > end) return false;
  if (!coverage) return true;
  let region = coverage.regions[0];
  if (area?.kind === 'bbox') {
    const [w, s, e, n] = area.bbox;
    region = coverage.regions.find((r) => w >= r.bbox[0] && e <= r.bbox[2] && s >= r.bbox[1] && n <= r.bbox[3]) ?? region;
  } else if (area?.kind === 'point') {
    const [lat, lon] = area.point;
    region = coverage.regions.find((r) => lon >= r.bbox[0] && lon <= r.bbox[2] && lat >= r.bbox[1] && lat <= r.bbox[3]) ?? region;
  }
  const covStart = region.start;
  const covEnd = region.latest_date ?? region.end;
  return start >= covStart && end <= covEnd;
}

export function isQueryValid(state: Pick<AppState, 'area' | 'start' | 'end'>, coverage?: CoverageResponse): boolean {
  return isAreaValid(state.area, coverage) && isDatesValid(state.start, state.end, coverage, state.area);
}
