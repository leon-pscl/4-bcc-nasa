import { describe, it, expect } from 'vitest';
import { textOn, COUNT_RAMP, quantileBins, countColor, binLabels } from './colors';

describe('colors', () => {
  it('textOn', () => {
    expect(textOn('#e31a1c')).toBe('#ffffff');
    expect(textOn('#b10026')).toBe('#ffffff');
    expect(textOn('#b2182b')).toBe('#ffffff');
    expect(textOn('#2166ac')).toBe('#ffffff');
    const dark = ['#e31a1c', '#b10026'];
    for (const c of COUNT_RAMP) expect(textOn(c)).toBe(dark.includes(c) ? '#ffffff' : '#0f0f0f');
  });
  it('quantile bins', () => {
    const bins = quantileBins([1,2,3,4,5,6,7,8,9,10], 7);
    expect(bins.length).toBe(7);
    expect(bins).toEqual([...bins].sort((a,b) => a-b));
  });
  it('countColor zero', () => {
    expect(countColor(0, [1,2])).toBe('#f0f0f0');
  });
  it('binLabels', () => {
    const labels = binLabels([4, 9, 25, 80, 148, 200, 245]);
    expect(labels[5]).toBe('149–200');
    expect(labels[6]).toBe('over 200');
    expect(labels).toHaveLength(7);
  });
});