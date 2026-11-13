import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AppHeader from './AppHeader';

vi.mock('../../api/hooks', () => ({
  useCoverage: () => ({ data: { regions: [{ latest_date: '2026-11-12', synthetic: true }], starter_areas: [] }, isLoading: false }),
}));

describe('AppHeader', () => {
  beforeEach(() => {
    const live = document.createElement('div');
    live.id = 'live-region';
    document.body.appendChild(live);
  });
  afterEach(() => {
    cleanup();
    document.getElementById('live-region')?.remove();
  });
  it('renders the date from the mock', () => {
    render(<AppHeader />);
    expect(screen.getByText(/Data through/)).toHaveTextContent('Data through 12 Nov 2026');
  });
  it('copy calls the clipboard and announces', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
    render(<AppHeader />);
    await user.click(screen.getByRole('button', { name: /Copy link/ }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalled();
      expect(document.getElementById('live-region')).toHaveTextContent('Link copied');
    });
  });
  it('does not claim success when the clipboard fails', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockRejectedValue(new Error('x')) }, configurable: true });
    render(<AppHeader />);
    await user.click(screen.getByRole('button', { name: /Copy link/ }));
    await waitFor(() => {
      expect(document.getElementById('live-region')).toHaveTextContent("Couldn't copy link");
    });
  });
});