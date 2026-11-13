import { describe, it, expect } from 'vitest';
import { parseEdges, areaKm2 } from './geo';

describe('geo', () => {
  it('rejects invalid edges', () => {
    expect(parseEdges('', '1', '2', '3')).toBeNull();
    expect(parseEdges('10', '-5', '0', '-5')).not.toBeNull(); // valid-ish
    expect(parseEdges('5', '10', '0', '-5')).toBeNull(); // south>=north
  });
  it('area ~ expected for Bolivia box', () => {
    const a = areaKm2(-14, -18, -60, -64);
    // R^2*(sin(-14)-sin(-18))*( (-60+64)deg in rad)
    expect(a).toBeGreaterThan(180000);
    expect(a).toBeLessThan(200000);
  });
});