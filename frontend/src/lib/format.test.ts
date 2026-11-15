import { describe, it, expect } from 'vitest';
import { formatNumber, formatSignedPct, formatDate, formatLat, formatDeg } from './format';

describe('format', () => {
  it('numbers', () => { expect(formatNumber(1234)).toBe('1,234'); });
  it('signed pct', () => {
    expect(formatSignedPct(40)).toBe('+40%');
    expect(formatSignedPct(-12)).toBe('\u221212%');
  });
  it('dates', () => { expect(formatDate('2026-11-12')).toBe('12 Nov 2026'); });
  it('lat', () => { expect(formatLat(-18)).toBe('18.0\u00b0S'); });
  it('formatDeg', () => {
    expect(formatDeg(-3.6, 'lat')).toBe('3.6°S');
    expect(formatDeg(110.7, 'lon')).toBe('110.7°E');
    expect(formatDeg(14.583583, 'lat')).toBe('14.5836°N');
    expect(formatDeg(-64, 'lon')).toBe('64°W');
    expect(formatDeg(0, 'lat')).toBe('0°');
    expect(formatDeg(180, 'lon')).toBe('180°');
  });
});