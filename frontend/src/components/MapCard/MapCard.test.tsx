import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MapCard from './MapCard';

vi.mock('../../state/useAppState', () => ({
  useAppState: () => ({ state: { area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] }, start: '2003-01-01', end: '2026-11-12', view: 'count', tab: 'comparisons' }, dispatch: vi.fn() }),
}));
vi.mock('../../api/hooks', () => ({
  useCoverage: () => ({ data: { regions: [
    { name: 'southeast_asia', bbox: [92.0, -11.0, 141.0, 28.5], synthetic: true, start: '2003-01-01', end: '2026-11-12', latest_date: '2026-11-12', countries: [], platforms: [], label: 'Southeast Asia' },
  ], starter_areas: [
    { name: 'central_kalimantan', label: 'Central Kalimantan', region: 'southeast_asia', bbox: [110.7, -3.6, 115.9, 0.8] },
  ] }, isLoading: false }),
}));

describe('MapCard', () => {
  afterEach(() => cleanup());

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

    // antimeridian rejected
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
});