import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OutlookPanel from './OutlookPanel';

import type { AppState } from '../../state/urlState';

const dispatch = vi.fn();
let state: AppState;

const outlook = {
  query: { bbox: [110.7, -3.6, 115.9, 0.8], area_km2: 282742.2 },
  issued: '2026-10',
  latest_data_date: '2026-11-14',
  unit: 'Hotspots (harmonized)',
  grid_deg: 0.15,
  threshold: 1,
  months: [
    { year: 2026, month: 11, lead: 1, model: 'climatology', expected: 320.0, typical_range: [120.0, 610.0], normal_mean: 320.0, normal_median: 157.0, observed_so_far: { through_day: 14, value: 1260.4 }, cells_likely: 312 },
    { year: 2026, month: 12, lead: 2, model: 'climatology', expected: 88.0, typical_range: [40.0, 95.0], normal_mean: 88.0, normal_median: 74.0, observed_so_far: null, cells_likely: 6 },
    { year: 2027, month: 1, lead: 3, model: 'climatology', expected: 135.6, typical_range: [69.5, 157.7], normal_mean: 135.6, normal_median: 108.8, observed_so_far: null, cells_likely: 7 },
  ],
  top_cells: [
    { lat: -2.025, lon: 113.925, lead: 1, p_fire: 0.94, expected: 21.3 },
    { lat: -1.875, lon: 115.875, lead: 1, p_fire: 0.88, expected: 7.5 },
    { lat: -2.925, lon: 115.875, lead: 1, p_fire: 0.83, expected: 4.5 },
    { lat: -2.025, lon: 113.925, lead: 2, p_fire: 0.85, expected: 3.4 },
    { lat: -1.875, lon: 115.875, lead: 2, p_fire: 0.59, expected: 2.0 },
    { lat: -2.025, lon: 113.925, lead: 3, p_fire: 0.50, expected: 1.0 },
  ],
  season: {
    normal_median: [12, 8, 3, 2, 1, 1, 2, 120, 250, 90, 30, 15],
    normal_mean: [15, 10, 4, 2, 1, 1, 3, 130, 260, 100, 40, 20],
    peak_month: 9,
    busiest_months: [9, 8, 10],
  },
  skill: { top10_capture_pct: 62.35, brier: 0.1132, test_years: [2015, 2025], big_years: { '2015': 63.03, '2019': 63.94, '2023': 63.43 } },
  synthetic: false,
  data_version: 'dv-mc-dv-o',
};

vi.mock('../../state/useAppState', () => ({ useAppState: () => ({ state, dispatch }) }));
vi.mock('../../api/hooks', () => ({
  useQueryParams: () => ({ params: 'bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-14', valid: true, coverage: { regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92.0, -11.0, 141.0, 28.5], countries: [], start: '2003-01-01', end: '2026-11-14', platforms: [], latest_date: '2026-11-14', synthetic: false }], starter_areas: [], data_version: 'dv' } }),
  useOutlook: () => ({ data: outlook, isLoading: false, isError: false }),
}));
vi.mock('react-chartjs-2', () => ({
  Bar: () => <canvas aria-label="outlook-chart" />,
}));
vi.mock('chart.js', () => ({
  Chart: { register: () => {}, defaults: { font: {} } },
  CategoryScale: {},
  LinearScale: {},
  BarElement: {},
  Tooltip: {},
  Legend: {},
}));

describe('OutlookPanel', () => {
  beforeEach(() => {
    dispatch.mockClear();
    state = {
      area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] },
      start: '2003-01-01', end: '2026-11-14', view: 'count', tab: 'outlook',
      cover: 'all', layer: 'history', lead: 1,
    };
  });
  afterEach(() => cleanup());

  it('renders the three month cards from the mock', () => {
    render(<OutlookPanel />);
    expect(screen.getByText('November 2026 · in progress')).toBeInTheDocument();
    expect(screen.getByText('December 2026')).toBeInTheDocument();
    expect(screen.getByText('January 2027')).toBeInTheDocument();
    expect(screen.getByText(/So far \(1–14 Nov\)/)).toBeInTheDocument();
    expect(screen.getByText(/typical range 120–610/)).toBeInTheDocument();
    expect(screen.getByText('1,260')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: "What's coming?" })).toBeInTheDocument();
    expect(screen.getByText(/Based on past fire patterns, not a weather forecast/)).toBeInTheDocument();
  });

  it('lists the top cells for the selected month, hottest first', () => {
    render(<OutlookPanel />);
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('94% chance');
    expect(rows[0]).toHaveTextContent('2.03°S, 113.93°E');
    expect(rows[1]).toHaveTextContent('88% chance');
    expect(rows[0]).toHaveTextContent('about 21 hotspots');
  });

  it('month switch dispatches the lead patch', async () => {
    const user = userEvent.setup();
    render(<OutlookPanel />);
    await user.click(screen.getByRole('button', { name: 'Dec' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { lead: 2 } });
  });

  it('Show on map dispatches layer, lead and the cell', async () => {
    const user = userEvent.setup();
    render(<OutlookPanel />);
    await user.click(screen.getByRole('button', { name: /Show cell 2\.03°S, 113\.93°E on the map/ }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { layer: 'outlook', lead: 1, cell: [-2.025, 113.925] } });
  });

  it('how reliable tiles show the backtest numbers and the link goes to Methods', async () => {
    const user = userEvent.setup();
    render(<OutlookPanel />);
    expect(screen.getByText('62%')).toBeInTheDocument();
    expect(screen.getByText('2015–2025')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'How the outlook works' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { tab: 'methods' } });
  });

  it('busiest months sentence renders from the mock season', () => {
    render(<OutlookPanel />);
    expect(screen.getByText(/Busiest months:/)).toBeInTheDocument();
    expect(screen.getByText(/Sep, Aug, Oct/)).toBeInTheDocument();
  });
});
