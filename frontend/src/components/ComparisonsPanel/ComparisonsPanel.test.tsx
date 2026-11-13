import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import ComparisonsPanel from './ComparisonsPanel';

import type { AppState } from '../../state/urlState';

const dispatch = vi.fn();
let state: AppState;

const cal = {
  query: { bbox: [110.7, -3.6, 115.9, 0.8], start: '2003-01-01', end: '2026-11-12', area_km2: 282742 },
  unit: 'Hotspots (harmonized)', years: [2024, 2025, 2026],
  values: [[1,2,3,4,5,6,7,8,9,10,11,12],[2,3,4,5,6,7,8,9,10,11,12,13],[3,4,5,6,7,8,9,10,11,115,null,null]],
  partial: { year: 2026, month: 11, through_day: 12 },
  monthly_median: [2,3,4,5,6,7,8,9,10,11,82,12], monthly_p25: [1,2,3,4,5,6,7,8,9,10,60,11], monthly_p75: [3,4,5,6,7,8,9,10,11,12,100,13],
  anomaly: [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,33,null]],
  anomaly_pct: [[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,40,null]],
  annual_totals: [78, 90, 178], partial_years: [2026], baseline_years: [2003, 2025],
  baseline_warning: null, coverage_warning: null, synthetic: false, data_version: 'v1',
};
const sum = { total: 346, peak_month: { year: 2025, month: 12, value: 13 }, peak_year: { year: 2025, value: 90 }, current_month: { year: 2026, month: 11, through_day: 12, value: 115, median_same_span: 82, pct_vs_median: 40 }, latest_data_date: '2026-11-12', synthetic: false, data_version: 'v1' };
const cov = { regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92,-11,141,28.5], countries: [], start: '2003-01-01', end: '2026-11-12', platforms: ['Aqua'], latest_date: '2026-11-12', synthetic: false }], starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7,-3.6,115.9,0.8] }], data_version: 'v1' };

vi.mock('../../state/useAppState', () => ({ useAppState: () => ({ state, dispatch }) }));
vi.mock('../../api/hooks', () => ({
  useCalendar: () => ({ data: cal, isLoading: false, error: null }),
  useSummary: () => ({ data: sum }),
  useCoverage: () => ({ data: cov }),
}));
vi.mock('react-chartjs-2', () => ({
  Line: () => <canvas aria-label="monthly-chart" />,
  Bar: () => <canvas aria-label="yearly-chart" />,
}));
vi.mock('chart.js', () => ({
  Chart: { register: () => {} },
  CategoryScale: {}, LinearScale: {}, PointElement: {}, LineElement: {}, BarElement: {}, Filler: {}, Tooltip: {}, Legend: {},
}));

describe('ComparisonsPanel', () => {
  beforeEach(() => { dispatch.mockClear(); state = { area: { kind: 'bbox', bbox: [110.7,-3.6,115.9,0.8] }, start: '2003-01-01', end: '2026-11-12', view: 'count', tab: 'comparisons' }; });
  afterEach(() => cleanup());

  it('shows current month comparison, badge, bars and stats', () => {
    render(<ComparisonsPanel />);
    expect(screen.getByText('How does this month compare?')).toBeInTheDocument();
    expect(screen.getByText(/November 2026, days 1-12/)).toBeInTheDocument();
    expect(screen.getAllByText('115').length).toBeGreaterThan(0);
    expect(screen.getByText(/40% above the median/)).toBeInTheDocument();
    expect(screen.getByLabelText(/This year 115 hotspots, median 82/)).toBeInTheDocument();
    expect(screen.getByText('346')).toBeInTheDocument(); // total
    expect(screen.getByText('Peak year')).toBeInTheDocument();
    expect(screen.getByText('Dec 2025')).toBeInTheDocument();
  });

  it('shows busiest months, legend and top years', () => {
    render(<ComparisonsPanel />);
    expect(screen.getByText(/Busiest months:/)).toHaveTextContent('Busiest months: Nov, Dec, Oct');
    expect(screen.getAllByText('Median').length).toBeGreaterThan(0);
    expect(screen.getByText('Middle half of years')).toBeInTheDocument();
    expect(screen.getByText('Top years (complete years only)')).toBeInTheDocument();
    expect(screen.getByText('90')).toBeInTheDocument();
  });
});
