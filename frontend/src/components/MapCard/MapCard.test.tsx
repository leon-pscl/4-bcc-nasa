import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import L from 'leaflet';
import MapCard from './MapCard';

const dispatch = vi.fn();
const state = { area: { kind: 'bbox' as const, bbox: [110.7, -3.6, 115.9, 0.8] as [number, number, number, number] }, start: '2003-01-01', end: '2026-11-12', view: 'count' as const, tab: 'comparisons' as const, cover: 'all' as const, layer: 'history' as 'history' | 'outlook', lead: 1 as 1 | 2 | 3, cell: undefined as [number, number] | undefined };

const coverage = { regions: [
  { name: 'southeast_asia', bbox: [92.0, -11.0, 141.0, 28.5], synthetic: true, start: '2003-01-01', end: '2026-11-12', latest_date: '2026-11-12', countries: [], platforms: [], label: 'Southeast Asia' },
], starter_areas: [
  { name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] },
], data_version: 'v' };

vi.mock('../../state/useAppState', () => ({
  useAppState: () => ({ state, dispatch }),
    useReadyAppState: () => ({ state, dispatch }),
}));
const outlookMock = {
  issued: '2026-10', latest_data_date: '2026-11-14', unit: 'Hotspots (harmonized)', grid_deg: 0.15, threshold: 1,
  query: { bbox: [110.7, -3.6, 115.9, 0.8], area_km2: 282742 },
  months: [
    { year: 2026, month: 11, lead: 1, model: 'climatology', expected: 727.6, typical_range: [180.9, 503.9], normal_mean: 727.6, normal_median: 267.0, observed_so_far: { through_day: 14, value: 1275.3 }, cells_likely: 60 },
    { year: 2026, month: 12, lead: 2, model: 'climatology', expected: 85.9, typical_range: [44.5, 95.4], normal_mean: 85.9, normal_median: 74.0, observed_so_far: null, cells_likely: 6 },
    { year: 2027, month: 1, lead: 3, model: 'climatology', expected: 135.6, typical_range: [69.5, 157.7], normal_mean: 135.6, normal_median: 108.8, observed_so_far: null, cells_likely: 7 },
  ],
  top_cells: Array.from({ length: 30 }, (_, i) => ({ lat: -2.025 + i * 0.01, lon: 113.925, lead: (i % 3) + 1, p_fire: 0.94 - i * 0.02, expected: 21.3 })),
  season: { normal_median: [12, 8, 3, 2, 1, 1, 2, 120, 250, 90, 30, 15], normal_mean: [], peak_month: 9, busiest_months: [9, 8, 10] },
  skill: { top10_capture_pct: 62.35, brier: 0.1132, test_years: [2015, 2025] },
  data_version: 'dv-mc-dv-o',
  synthetic: false,
};
const outlookMapMock = {
  grid_deg: 0.15, issued: '2026-10', target: { year: 2026, month: 11 }, model: 'climatology', data_version: 'dv-mc-dv-o',
  cells: [
    { lat: -3.525, lon: 114.975, p_fire: 0.94, expected: 21.3, mean_clim: 21.3 },
    { lat: -3.375, lon: 114.825, p_fire: 0.05, expected: 0.4, mean_clim: 0.4 },
  ],
};
vi.mock('../../api/hooks', () => ({
  useCoverage: () => ({ data: coverage, isLoading: false }),
  useQueryParams: () => ({ params: 'bbox=110.7,-3.6,115.9,0.8&start=2003-01-01&end=2026-11-12', valid: true, coverage }),
  useMap: () => ({ data: { grid_deg: 0.05, aggregated_to: null, cells: [], data_version: 'v' } }),
  useCalendar: () => ({ data: null }),
  useOutlook: () => ({ data: outlookMock, isLoading: false }),
  useOutlookMap: () => ({ data: outlookMapMock, isLoading: false }),
}));

describe('MapCard', () => {
  beforeEach(() => dispatch.mockClear());
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('draft starts from applied area and typing redraws the box', async () => {
    render(<MapCard />);
    const north = screen.getByLabelText('North edge') as HTMLInputElement;
    expect(north.value).toBe('0.8');
    expect(screen.getByText('282,742 km²')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.clear(north);
    await user.type(north, '0.5');
    expect((screen.getByLabelText('North edge') as HTMLInputElement).value).toBe('0.5');
  });

  it('typing "-", "" or "abc" never throws', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const north = screen.getByLabelText('North edge') as HTMLInputElement;
    await user.clear(north);
    await user.type(north, '-');
    expect(north.value).toBe('-');
    await user.clear(north);
    await user.type(north, 'abc');
    expect(north.value).toBe('abc');
    await user.clear(north);
    expect(north.value).toBe('');
    expect(screen.getByText(/Enter all four edges/)).toBeInTheDocument();
  });

  it('invalid input and antimeridian disable Analyze', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText('North edge'));
    await user.type(screen.getByLabelText('North edge'), '100');
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
    expect(screen.getByText(/North and South/)).toBeInTheDocument();

    await user.clear(screen.getByLabelText('North edge'));
    await user.type(screen.getByLabelText('North edge'), '10');
    await user.clear(screen.getByLabelText('South edge'));
    await user.type(screen.getByLabelText('South edge'), '-10');
    await user.clear(screen.getByLabelText('East edge'));
    await user.type(screen.getByLabelText('East edge'), '-170');
    await user.clear(screen.getByLabelText('West edge'));
    await user.type(screen.getByLabelText('West edge'), '170');
    expect(screen.getByText(/180° line/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
  });

  it('over 500,000 km² disables Analyze', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText('North edge'));
    await user.type(screen.getByLabelText('North edge'), '80');
    await user.clear(screen.getByLabelText('South edge'));
    await user.type(screen.getByLabelText('South edge'), '-80');
    await user.clear(screen.getByLabelText('East edge'));
    await user.type(screen.getByLabelText('East edge'), '170');
    await user.clear(screen.getByLabelText('West edge'));
    await user.type(screen.getByLabelText('West edge'), '-170');
    expect(screen.getByText(/500,000 km² limit/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
  });

  it('date presets produce the right range for a fixed latest_date', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const start = screen.getByLabelText('Start') as HTMLInputElement;
    const end = screen.getByLabelText('End') as HTMLInputElement;
    expect(end.value).toBe('2026-11-12');

    await user.click(screen.getByRole('button', { name: 'Last 30 days' }));
    expect(start.value).toBe('2026-10-14');
    expect(end.value).toBe('2026-11-12');

    await user.click(screen.getByRole('button', { name: 'This year' }));
    expect(start.value).toBe('2026-01-01');

    await user.click(screen.getByRole('button', { name: 'Last 5 years' }));
    expect(start.value).toBe('2022-01-01');

    await user.click(screen.getByRole('button', { name: 'Full record' }));
    expect(start.value).toBe('2003-01-01');
    expect(end.value).toBe('2026-11-12');
  });

  it('date errors and Enter submits; no request until Analyze', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const start = screen.getByLabelText('Start') as HTMLInputElement;
    const end = screen.getByLabelText('End') as HTMLInputElement;

    await user.clear(end);
    expect(screen.getByText('Choose a start date and an end date.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();

    await user.type(end, '2026-11-12');
    await user.clear(start);
    await user.type(start, '2026-12-01');
    expect(screen.getByText('The start date must be before the end date.')).toBeInTheDocument();

    await user.clear(start);
    await user.type(start, '2003-01-01');
    expect(dispatch).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    expect(dispatch).toHaveBeenCalled();
  });

  function spyMap() {
    const fit = vi.spyOn(L.Map.prototype, 'fitBounds').mockImplementation(function (this: L.Map) { return this; });
    const setView = vi.spyOn(L.Map.prototype, 'setView');
    const setZoom = vi.spyOn(L.Map.prototype, 'setZoom');
    return { fit, setView, setZoom };
  }

  function fireMap(map: L.Map, type: string, latlng: { lat: number; lng: number }, containerPoint: { x: number; y: number }) {
    act(() => { map.fire(type, { latlng, containerPoint, originalEvent: {} }); });
  }

  it('typing in an edge field does not move the map', async () => {
    const { fit } = spyMap();
    render(<MapCard />);
    expect(fit).toHaveBeenCalledTimes(1);
    const user = userEvent.setup();
    const west = screen.getByLabelText('West edge');
    await user.clear(west);
    await user.type(west, '1');
    expect(fit).toHaveBeenCalledTimes(1);
    await user.type(west, '1');
    expect(fit).toHaveBeenCalledTimes(1);
    await user.type(west, '0');
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('drawing a box does not move the map and fills the fields', async () => {
    const { fit, setView, setZoom } = spyMap();
    render(<MapCard />);
    expect(fit).toHaveBeenCalledTimes(1);
    setView.mockClear(); setZoom.mockClear();
    const map = fit.mock.contexts[0] as L.Map;
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Draw area' }));

    fireMap(map, 'mousedown', { lat: 0, lng: 112 }, { x: 10, y: 10 });
    fireMap(map, 'mousemove', { lat: -0.5, lng: 112.5 }, { x: 20, y: 20 });
    fireMap(map, 'mousemove', { lat: -1, lng: 113 }, { x: 30, y: 30 });
    fireMap(map, 'mousemove', { lat: -2, lng: 114 }, { x: 60, y: 60 });

    expect(screen.getByText('North 0°')).toBeInTheDocument();
    expect(screen.getByText('South 2°S')).toBeInTheDocument();
    expect(screen.getByText('West 112°E')).toBeInTheDocument();
    expect(screen.getByText('East 114°E')).toBeInTheDocument();

    fireMap(map, 'mouseup', { lat: -2, lng: 114 }, { x: 60, y: 60 });
    expect(fit).toHaveBeenCalledTimes(1);
    expect(setView).not.toHaveBeenCalled();
    expect(setZoom).not.toHaveBeenCalled();
    expect((screen.getByLabelText('North edge') as HTMLInputElement).value).toBe('0');
    expect((screen.getByLabelText('South edge') as HTMLInputElement).value).toBe('-2');
    expect((screen.getByLabelText('West edge') as HTMLInputElement).value).toBe('112');
    expect((screen.getByLabelText('East edge') as HTMLInputElement).value).toBe('114');
  });

  it('a click without a drag keeps draw mode and leaves the fields alone', async () => {
    const { fit } = spyMap();
    render(<MapCard />);
    const map = fit.mock.contexts[0] as L.Map;
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Draw area' }));
    fireMap(map, 'mousedown', { lat: 1, lng: 113 }, { x: 40, y: 40 });
    fireMap(map, 'mouseup', { lat: 1, lng: 113 }, { x: 42, y: 41 });
    expect((screen.getByLabelText('North edge') as HTMLInputElement).value).toBe('0.8');
    expect((screen.getByLabelText('South edge') as HTMLInputElement).value).toBe('-3.6');
    expect(screen.getByRole('button', { name: 'Draw area' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('releasing outside the map ends the box at the last position', async () => {
    const { fit } = spyMap();
    render(<MapCard />);
    const map = fit.mock.contexts[0] as L.Map;
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Draw area' }));
    fireMap(map, 'mousedown', { lat: 1, lng: 113 }, { x: 10, y: 10 });
    fireMap(map, 'mousemove', { lat: -1, lng: 115 }, { x: 50, y: 50 });
    fireEvent.mouseUp(document.body);
    expect((screen.getByLabelText('North edge') as HTMLInputElement).value).toBe('1');
    expect((screen.getByLabelText('South edge') as HTMLInputElement).value).toBe('-1');
    expect((screen.getByLabelText('West edge') as HTMLInputElement).value).toBe('113');
    expect((screen.getByLabelText('East edge') as HTMLInputElement).value).toBe('115');
    expect(screen.getByRole('button', { name: 'Draw area' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('Analyze fits once; outside changes fit; dates do not', async () => {
    const { fit } = spyMap();
    const { rerender } = render(<MapCard />);
    expect(fit).toHaveBeenCalledTimes(1);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Analyze/ }));
    expect(fit).toHaveBeenCalledTimes(2);

    const originalArea = state.area;
    const originalStart = state.start;
    const originalEnd = state.end;
    state.area = { kind: 'bbox', bbox: [111, -4, 116.5, 1] as [number, number, number, number] };
    rerender(<MapCard />);
    expect(fit).toHaveBeenCalledTimes(3);

    state.start = '2004-05-01';
    rerender(<MapCard />);
    expect(fit).toHaveBeenCalledTimes(3);

    state.area = originalArea;
    state.start = originalStart;
    state.end = originalEnd;
  });

  it('Esc cancels drawing without changing the fields', async () => {
    const { fit } = spyMap();
    render(<MapCard />);
    const map = fit.mock.contexts[0] as L.Map;
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Draw area' }));
    fireMap(map, 'mousedown', { lat: 0, lng: 112 }, { x: 10, y: 10 });
    fireMap(map, 'mousemove', { lat: -2, lng: 114 }, { x: 60, y: 60 });
    act(() => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
    expect((screen.getByLabelText('North edge') as HTMLInputElement).value).toBe('0.8');
    expect((screen.getByLabelText('South edge') as HTMLInputElement).value).toBe('-3.6');
    expect(screen.getByRole('button', { name: 'Draw area' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows side labels for the draft box', async () => {
    render(<MapCard />);
    expect(screen.getByText('North 0.8°N')).toBeInTheDocument();
    expect(screen.getByText('South 3.6°S')).toBeInTheDocument();
    expect(screen.getByText('West 110.7°E')).toBeInTheDocument();
    expect(screen.getByText('East 115.9°E')).toBeInTheDocument();
  });

  it('side label follows the South field value', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const south = screen.getByLabelText('South edge');
    await user.clear(south);
    await user.type(south, '-4');
    expect(screen.getByText('South 4°S')).toBeInTheDocument();
  });

  it('layer switch: History | Outlook buttons dispatch the layer patch', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const outlookBtn = screen.getByRole('button', { name: 'Outlook' });
    const historyBtn = screen.getByRole('button', { name: 'History' });
    expect(historyBtn).toHaveAttribute('aria-pressed', 'true');
    expect(outlookBtn).toHaveAttribute('aria-pressed', 'false');
    await user.click(outlookBtn);
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { layer: 'outlook' } });
  });

  it('outlook layer renders outlook cells and the month switch', async () => {
    const originalLayer = state.layer;
    state.layer = 'outlook';
    render(<MapCard />);
    expect(screen.getByRole('group', { name: 'Outlook month' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nov' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/15 km cells/)).toBeInTheDocument();
    state.layer = originalLayer;
  });

  it('outlook month switch dispatches the lead patch', async () => {
    const originalLayer = state.layer;
    state.layer = 'outlook';
    render(<MapCard />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Dec' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { lead: 2 } });
    state.layer = originalLayer;
  });

  it('edge fields are in DOM order North, West, East, South', () => {
    render(<MapCard />);
    const n = screen.getByLabelText('North edge');
    const w = screen.getByLabelText('West edge');
    const e = screen.getByLabelText('East edge');
    const s = screen.getByLabelText('South edge');
    expect(n.compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(w.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(e.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
