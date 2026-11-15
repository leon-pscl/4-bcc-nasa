import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import Downloads from './Downloads';

const dispatch = vi.fn();
const state = {
  area: { kind: 'bbox' as const, bbox: [110.7, -3.6, 115.9, 0.8] as [number, number, number, number] },
  start: '2003-01-01', end: '2026-11-14', view: 'count' as const,
  tab: 'comparisons' as const, cover: 'all' as const, layer: 'history' as const, lead: 1 as const,
};

vi.mock('../../state/useAppState', () => ({ useAppState: () => ({ state, dispatch }),
    useReadyAppState: () => ({ state, dispatch }) }));
vi.mock('../../api/hooks', () => ({
  useQueryParams: () => ({
    params: 'bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-14&cover=all',
    valid: true,
    coverage: { regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92, -11, 141, 28.5], countries: [], start: '2003-01-01', end: '2026-11-14', platforms: [], latest_date: '2026-11-14', synthetic: false }], starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] }], data_version: 'dv' },
  }),
}));

describe('Downloads', () => {
  beforeEach(() => dispatch.mockClear());
  afterEach(() => cleanup());

  it('renders the outlook and cells download links with the right hrefs', () => {
    render(<Downloads />);
    expect(screen.getByRole('link', { name: 'Outlook CSV' }))
      .toHaveAttribute('href', '/api/outlook.csv?bbox=110.7,-3.6,115.9,0.8');
    expect(screen.getByRole('link', { name: 'Monthly 15 km cells CSV' }))
      .toHaveAttribute('href', '/api/cells.csv?bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-14');
    expect(screen.getByRole('link', { name: 'Monthly 15 km cells Parquet' }))
      .toHaveAttribute('href', '/api/cells.parquet?bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-14');
    expect(screen.getByText(/One row per cell and month with fire/)).toBeInTheDocument();
  });
});

