import { describe, it, expect } from 'vitest';
import { parseHash, toHash, type AppState } from './urlState';

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
});