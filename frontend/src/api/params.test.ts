import { describe, it, expect } from 'vitest';
import { isQueryValid, buildQueryParams } from './params';
import type { AppState } from '../state/urlState';
import type { CoverageResponse } from './schemas';

const cov: CoverageResponse = {
  regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92, -11, 141, 28.5], countries: [], start: '2003-01-01', end: '2026-11-14', platforms: [], latest_date: '2026-11-14', synthetic: false }],
  starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] }],
  data_version: 'v',
};

describe('params', () => {
  it('invalid state means no params/fetch', () => {
    const bad: AppState = { area: { kind: 'bbox', bbox: [0, 0, 0, 0] }, start: '', end: '', view: 'count', tab: 'comparisons', cover: 'all' };
    expect(isQueryValid(bad, cov)).toBe(false);
    expect(isQueryValid({ ...bad, area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }, start: '2025-01-01', end: '2024-01-01' }, cov)).toBe(false);
  });
  it('valid state builds params', () => {
    const ok: AppState = { area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }, start: '2003-01-01', end: '2026-11-14', view: 'count', tab: 'comparisons', cover: 'all' };
    expect(isQueryValid(ok, cov)).toBe(true);
    expect(buildQueryParams(ok)).toContain('bbox=');
  });
});
