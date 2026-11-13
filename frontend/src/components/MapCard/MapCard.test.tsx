import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MapCard from './MapCard';

vi.mock('../../state/useAppState', () => ({
  useAppState: () => ({ state: { area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }, start: '2003-01-01', end: '2026-11-12', view: 'count', tab: 'comparisons' }, dispatch: vi.fn() }),
}));
vi.mock('../../api/hooks', () => ({
  useCoverage: () => ({ data: { regions: [{ name: 'southeast_asia', bbox: [92.0, -11.0, 141.0, 28.5], synthetic: true, start: '2003-01-01', end: '2026-11-12', latest_date: '2026-11-12', countries: [], platforms: [], label: 'Southeast Asia' }], starter_areas: [{ name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] }, { name: 'bolivia_east', label: 'East Bolivia', region: 'amazon', bbox: [-64, -18, -60, -14] }] }, isLoading: false }),
}));

describe('MapCard', () => {
  afterEach(() => cleanup());
  it('draft starts from applied area and validates', async () => {
    render(<MapCard />);
    const north = screen.getByLabelText('North edge') as HTMLInputElement;
    expect(north.value).toBe('0.8');
    expect(screen.getByText('282,742 km²')).toBeInTheDocument();
  });
  it('invalid input disables Analyze', async () => {
    render(<MapCard />);
    const north = screen.getByLabelText('North edge') as HTMLInputElement;
    const user = userEvent.setup();
    await user.clear(north);
    await user.type(north, '100');
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
    expect(screen.getByText(/North and South/)).toBeInTheDocument();
  });
  it('outside region disables Analyze', async () => {
    render(<MapCard />);
    const user = userEvent.setup();
    const north = screen.getByLabelText('North edge') as HTMLInputElement;
    const south = screen.getByLabelText('South edge') as HTMLInputElement;
    await user.clear(north); await user.type(north, '-14');
    await user.clear(south); await user.type(south, '-18');
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
  });
});