import { describe, it, expect } from 'vitest';
import { parseEdges, areaKm2, wrapLon, round4, validateEdges, insideRegion, MAX_AREA_KM2 } from './geo';

describe('geo', () => {
  it('parseEdges rejects invalid', () => { expect(parseEdges('10', '20', '30', '40')).toBeNull(); });
  it('areaKm2 positive', () => { expect(areaKm2(-14, -18, -60, -64)).toBeGreaterThan(0); });
  it('wrapLon', () => { expect(wrapLon(190)).toBe(-170); });
  it('round4', () => { expect(round4(1.123456)).toBe(1.1235); });

  it('validateEdges messages', () => {
    expect(validateEdges('', '', '', '')).toBe('Enter all four edges in decimal degrees.');
    expect(validateEdges('100', '-18', '-60', '-64')).toBe('North and South must be between −90 and 90.');
    expect(validateEdges('-14', '-18', '200', '-64')).toBe('East and West must be between −180 and 180.');
    expect(validateEdges('-18', '-14', '-60', '-64')).toBe('The South edge must be below the North edge.');
    expect(validateEdges('-14', '-18', '-64', '-60')).toBe("The West edge must be left of the East edge (areas can't cross the 180° line).");
    expect(validateEdges('80', '-80', '170', '-170')).toBe('Larger than the 500,000 km² limit. Draw a smaller area.');
    expect(validateEdges('-14', '-18', '-60', '-64')).toBeNull();
    expect(areaKm2(80, -80, 170, -170)).toBeGreaterThan(MAX_AREA_KM2);
  });

  it('insideRegion', () => {
    const edges = { n: -3.5, s: -3.6, e: 115.9, w: 115.8 };
    expect(insideRegion(edges, [110.7, -3.6, 115.9, 0.8])).toBe(true);
    expect(insideRegion(edges, [97.3, 17.0, 101.5, 20.5])).toBe(false);
  });
});