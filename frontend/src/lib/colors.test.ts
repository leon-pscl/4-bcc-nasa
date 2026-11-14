import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { textOn, COUNT_RAMP, countBins, countColor, binLabels } from './colors';

describe('colors', () => {
  it('textOn', () => {
    expect(textOn('#e31a1c')).toBe('#ffffff');
    expect(textOn('#b10026')).toBe('#ffffff');
    expect(textOn('#b2182b')).toBe('#ffffff');
    expect(textOn('#2166ac')).toBe('#ffffff');
    const dark = ['#e31a1c', '#b10026'];
    for (const c of COUNT_RAMP) expect(textOn(c)).toBe(dark.includes(c) ? '#ffffff' : '#0f0f0f');
  });
  it('count bins', () => {
    const bins = countBins([1,2,3,4,5,6,7,8,9,10,100,1000], 7);
    expect(bins.length).toBe(7);
    expect(bins[6]).toBeGreaterThan(0);
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
  it('real mock: Sep 2015 and Sep 2017 land in different bins', () => {
    const calPath = path.join(process.cwd(), 'public', 'mock', 'api_calendar.json');
    const cal = JSON.parse(readFileSync(calPath, 'utf8')) as { years: number[]; values: (number | null)[][] };
    const i2015 = cal.years.indexOf(2015);
    const i2017 = cal.years.indexOf(2017);
    const sep2015 = cal.values[i2015][8] as number;
    const sep2017 = cal.values[i2017][8] as number;
    const vals = cal.values.flat().filter((v): v is number => v !== null && v > 0);
    const bins = countBins(vals);
    const idx = (v: number) => { let i = bins.findIndex((b) => v <= b); if (i < 0) i = bins.length - 1; return i; };
    expect(idx(sep2015)).not.toBe(idx(sep2017));
  });
});