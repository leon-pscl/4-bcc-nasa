import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BurningCalendar from './BurningCalendar';

const dispatch = vi.fn();
let state: { area: { kind: 'bbox'; bbox: [number, number, number, number] }; start: string; end: string; view: 'count' | 'anomaly'; tab: 'comparisons' | 'watchlist' | 'methods'; focus?: string };

const cal = {
  query: { bbox: [110.7, -3.6, 115.9, 0.8], start: '2003-01-01', end: '2026-11-12', area_km2: 282742 },
  unit: 'Hotspots (harmonized)',
  years: [2025, 2026],
  values: [[10.4, 0, 0.4, 0,0,0,0,0,0,0,0,0],[5,0,0,0,0,0,0,0,0,0,115,null]],
  partial: { year: 2026, month: 11, through_day: 12 },
  monthly_median: [10,0,1,0,0,0,0,0,0,0,82,0],
  monthly_p25: [8,0,0,0,0,0,0,0,0,0,60,0],
  monthly_p75: [12,0,2,0,0,0,0,0,0,0,100,0],
  anomaly: [[0.4,0,-0.6,0,0,0,0,0,0,0,0,0],[-5,0,0,0,0,0,0,0,0,0,33,null]],
  anomaly_pct: [[4, null, -60, null,null,null,null,null,null,null,null,null],[-50,null,null,null,null,null,null,null,null,null,40,null]],
  annual_totals: [10.8, 120],
  partial_years: [2026],
  baseline_years: [2003, 2025],
  baseline_warning: null,
  coverage_warning: null,
  synthetic: true,
  data_version: 'v1',
};
const sum = { total: 130.8, peak_month: null, peak_year: null, current_month: { year: 2026, month: 11, through_day: 12, value: 115, median_same_span: 82, pct_vs_median: 40 }, latest_data_date: '2026-11-12', synthetic: true, data_version: 'v1' };
const cov = { regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92,-11,141,28.5], countries: [], start: '2003-01-01', end: '2026-11-12', platforms: ['Aqua'], latest_date: '2026-11-12', synthetic: true }], starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7,-3.6,115.9,0.8] }], data_version: 'v1' };

vi.mock('../../state/useAppState', () => ({ useAppState: () => ({ state, dispatch }) }));
vi.mock('../../api/hooks', () => ({
  useCalendar: () => ({ data: cal, isLoading: false, error: null }),
  useSummary: () => ({ data: sum }),
  useCoverage: () => ({ data: cov }),
  useQueryParams: () => ({ params: 'bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-12', valid: true, coverage: cov }),
}));

describe('BurningCalendar', () => {
  beforeEach(() => {
    dispatch.mockClear();
    state = { area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }, start: '2003-01-01', end: '2026-11-12', view: 'count', tab: 'comparisons', focus: undefined };
  });
  afterEach(() => cleanup());

  it('renders rounded numbers and newest year first', () => {
    render(<BurningCalendar />);
    expect(screen.queryByText('10.4')).not.toBeInTheDocument();
    expect(screen.getByLabelText('January 2025: 10 hotspots, 4% above the median')).toHaveTextContent('10');
    expect(screen.getByText('<1')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(within(rows[1]).getByText('2026')).toBeInTheDocument();
    expect(within(rows[2]).getByText('2025')).toBeInTheDocument();
  });

  it('cell has right label and view switch changes text and legend', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<BurningCalendar />);
    expect(screen.getByLabelText('January 2025: 10 hotspots, 4% above the median')).toBeInTheDocument();
    expect(screen.getByText('Hotspots per month')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Anomaly vs median' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { view: 'anomaly' } });
    state.view = 'anomaly';
    rerender(<BurningCalendar />);
    expect(screen.getByText('Difference from the monthly median')).toBeInTheDocument();
    expect(screen.getByLabelText('January 2025: 10 hotspots, 4% above the median')).toHaveTextContent('+4%');
  });

  it('partial cell shows SO FAR and uses same-days %', () => {
    const { rerender } = render(<BurningCalendar />);
    expect(screen.getByText(/SO FAR/)).toBeInTheDocument();
    expect(screen.getByLabelText(/November 2026, days 1 to 12 so far: 115 hotspots, 40% above the median for the same days/)).toBeInTheDocument();
    state.view = 'anomaly';
    rerender(<BurningCalendar />);
    const partial = screen.getByLabelText(/November 2026, days 1 to 12 so far/);
    expect(partial).toHaveTextContent('+40%');
    expect(partial).toHaveTextContent('SO FAR');
  });

  it('selecting a cell updates focus', async () => {
    const user = userEvent.setup();
    render(<BurningCalendar />);
    await user.click(screen.getByLabelText('January 2025: 10 hotspots, 4% above the median'));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { focus: '2025-01' } });
  });
});