import type { AppState, AreaState } from '../state/urlState';
import type { CoverageResponse } from './schemas';
import { areaKm2, MAX_AREA_KM2 } from '../lib/geo';

export function buildAreaParams(area: AreaState): string {
  return `bbox=${area.bbox.join(',')}`;
}

export function buildQueryParams(state: Pick<AppState, 'area' | 'start' | 'end' | 'cover'>): string {
  const parts = [buildAreaParams(state.area), `start=${state.start}`, `end=${state.end}`];
  if (state.cover) parts.push(`cover=${state.cover}`);
  return parts.join('&');
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
  return true;
}

export function isDatesValid(start: string, end: string, coverage?: CoverageResponse, area?: AreaState): boolean {
  if (!start || !end || start > end) return false;
  if (!coverage) return true;
  let region = coverage.regions[0];
  if (area?.kind === 'bbox') {
    const [w, s, e, n] = area.bbox;
    region = coverage.regions.find((r) => w >= r.bbox[0] && e <= r.bbox[2] && s >= r.bbox[1] && n <= r.bbox[3]) ?? region;
  }
  const covStart = region.start;
  const covEnd = region.latest_date ?? region.end;
  return start >= covStart && end <= covEnd;
}

export function isQueryValid(state: Pick<AppState, 'area' | 'start' | 'end'>, coverage?: CoverageResponse): boolean {
  return isAreaValid(state.area, coverage) && isDatesValid(state.start, state.end, coverage, state.area);
}
