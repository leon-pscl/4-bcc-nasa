import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import HotspotTable from './HotspotTable';

const hotspots = vi.hoisted(() => ({ data: undefined as unknown, isFetching: false }));

vi.mock('../../state/useAppState', () => ({
  useReadyAppState: () => ({
    state: { area: { kind: 'bbox', bbox: [-65, -10, -61, -2] }, start: '2003-01-01', end: '2026-11-14', cover: 'all', focus: undefined },
    dispatch: vi.fn(),
  }),
}));

vi.mock('../../api/hooks', () => ({
  useQueryParams: () => ({ valid: true }),
  useHotspots: () => hotspots,
}));

describe('HotspotTable', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      disconnect() {}
    });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows loading, not "No hotspots", while the query is disabled', () => {
    render(<HotspotTable />);
    expect(screen.getByText('Loading hotspots…')).toBeInTheDocument();
    expect(screen.queryByText('No hotspots in this area and date range.')).not.toBeInTheDocument();
    expect(screen.queryByText('0 detections')).not.toBeInTheDocument();
  });
});
