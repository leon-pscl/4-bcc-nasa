import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import SyntheticBanner from './SyntheticBanner';

const mock = { synthetic: true };
vi.mock('../../api/hooks', () => ({
  useCoverage: () => ({ data: { regions: [{ latest_date: '2026-11-12', synthetic: mock.synthetic }], starter_areas: [] }, isLoading: false }),
}));

describe('SyntheticBanner', () => {
  afterEach(() => cleanup());
  it('shown for synthetic: true', () => {
    mock.synthetic = true;
    render(<SyntheticBanner />);
    expect(screen.getByRole('status')).toHaveTextContent('SYNTHETIC DATA');
  });
  it('hidden for synthetic: false', () => {
    mock.synthetic = false;
    render(<SyntheticBanner />);
    expect(screen.queryByRole('status')).toBeNull();
  });
});