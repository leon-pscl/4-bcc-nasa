import { describe, it, expect } from 'vitest';
import { formatNumber, formatSignedPct, formatDate, formatLat } from './format';

describe('format', () => {
  it('numbers', () => { expect(formatNumber(1234)).toBe('1,234'); });
  it('signed pct', () => {
    expect(formatSignedPct(40)).toBe('+40%');
    expect(formatSignedPct(-12)).toBe('\u221212%');
  });
  it('dates', () => { expect(formatDate('2026-11-12')).toBe('12 Nov 2026'); });
  it('lat', () => { expect(formatLat(-18)).toBe('18.0\u00b0S'); });
});