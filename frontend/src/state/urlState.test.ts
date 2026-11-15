import { describe, it, expect } from 'vitest';
import { parseHash, toHash, areaKey, type AppState } from './urlState';

describe('urlState', () => {
  const state: AppState = {
    area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] },
    start: '2003-01-01',
    end: '2026-11-12',
    view: 'count',
    tab: 'comparisons',
    cover: 'all',
  };
  it('round trip', () => {
    const h = toHash(state);
    expect(parseHash(h)).toEqual(state);
  });
  it('tab=watchlist falls back to comparisons', () => {
    expect(parseHash('#tab=watchlist').tab).toBeUndefined();
    expect(parseHash('#tab=methods').tab).toBe('methods');
    expect(parseHash('#tab=comparisons').tab).toBe('comparisons');
  });
  it('areaKey is fixed-order and independent of object literal key order', () => {
    expect(areaKey({ kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] })).toBe('bbox:110.7,-3.6,115.9,0.8');
    const reordered = { bbox: [110.7, -3.6, 115.9, 0.8], kind: 'bbox' } as unknown as typeof state.area;
    expect(areaKey(reordered)).toBe(areaKey(state.area));
    expect(areaKey({ kind: 'point', point: [1.5, 103.8], radius_km: 25 })).toBe('point:1.5,103.8:25');
    expect(areaKey({ kind: 'point', radius_km: 25, point: [1.5, 103.8] } as unknown as typeof state.area))
      .toBe('point:1.5,103.8:25');
    expect(areaKey({ kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }))
      .not.toBe(areaKey({ kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.9] }));
  });
});