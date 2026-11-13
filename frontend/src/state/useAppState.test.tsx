import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { AppStateProvider, useAppState } from './useAppState';

const cov = {
  regions: [{ name: 'southeast_asia', label: 'Southeast Asia', bbox: [92, -11, 141, 28.5], countries: [], start: '2003-01-01', end: '2026-11-14', platforms: [], latest_date: '2026-11-14', synthetic: false }],
  starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] }],
  data_version: 'v',
};

vi.mock('../api/hooks', () => ({ useCoverage: () => ({ data: cov }) }));

function Probe() {
  const { state } = useAppState();
  return <pre data-testid="state">{JSON.stringify(state)}</pre>;
}

describe('useAppState init', () => {
  beforeEach(() => { window.location.hash = ''; });
  afterEach(() => { cleanup(); window.location.hash = ''; });

  it('partial hash "#tab=comparisons" gives starter area and full dates', async () => {
    window.location.hash = '#tab=comparisons';
    render(<AppStateProvider><Probe /></AppStateProvider>);
    const el = await screen.findByTestId('state');
    const s = JSON.parse(el.textContent || '{}');
    expect(s.tab).toBe('comparisons');
    expect(s.area).toEqual({ kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] });
    expect(s.start).toBe('2003-01-01');
    expect(s.end).toBe('2026-11-14');
  });
});
