import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';
import HotspotTable from './HotspotTable';
import { ApiError } from '../../api/client';

const hotspots = vi.hoisted(() => ({ data: undefined as unknown, isFetching: false, error: null as Error | null }));
let observerCallback: IntersectionObserverCallback | null = null;

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
    hotspots.error = null;
    observerCallback = null;
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) { observerCallback = callback; }
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

  it('shows the ApiError instead of loading once visible', () => {
    hotspots.error = new ApiError(500, 'internal server error');
    render(<HotspotTable />);
    act(() => observerCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByText('Couldn’t load hotspots (500 – internal server error).')).toBeInTheDocument();
    expect(screen.queryByText('Loading hotspots…')).not.toBeInTheDocument();
    expect(screen.queryByText('0 detections')).not.toBeInTheDocument();
  });
});
