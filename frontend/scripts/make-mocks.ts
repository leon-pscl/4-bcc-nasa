import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const out = join(process.cwd(), 'public', 'mock');
mkdirSync(out, { recursive: true });

const years = Array.from({ length: 2026 - 2003 + 1 }, (_, i) => 2003 + i);
const peak = [0.2, 0.15, 0.25, 0.3, 0.4, 0.6, 0.9, 1.0, 0.95, 0.7, 0.4, 0.25];
const values = years.map((y, yi) => peak.map((p) => Math.round((200 + yi * 5) * p)));
const annual = values.map((v) => v.reduce((a, b) => a + b, 0));

const mock = {
  query: { bbox: [110.7, -3.6, 115.9, 0.8], start: '2003-01-01', end: '2026-11-12', area_km2: 282742 },
  unit: 'Hotspots (harmonized)',
  years,
  values,
  partial: { year: 2026, month: 11, through_day: 12 },
  monthly_median: peak.map((p) => Math.round(220 * p)),
  monthly_p25: peak.map((p) => Math.round(180 * p)),
  monthly_p75: peak.map((p) => Math.round(260 * p)),
  anomaly: values.map((v) => v.map(() => 0)),
  anomaly_pct: values.map((v) => v.map(() => 0)),
  annual_totals: annual,
  partial_years: [2026],
  baseline_years: [2003, 2025],
  baseline_warning: null,
  coverage_warning: null,
  synthetic: true,
  data_version: '2026-11-13T00:00:00Z',
};

writeFileSync(join(out, 'api_calendar.json'), JSON.stringify(mock, null, 2));
console.log('wrote api_calendar.json');