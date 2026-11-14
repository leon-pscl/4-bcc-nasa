import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SidePanel from './SidePanel';

import type { AppState } from '../../state/urlState';

const dispatch = vi.fn();
let state: Pick<AppState, 'tab'>;

vi.mock('../../state/useAppState', () => ({ useAppState: () => ({ state, dispatch }) }));
vi.mock('../ComparisonsPanel/ComparisonsPanel', () => ({ default: () => <div>Comparisons content</div> }));

describe('SidePanel', () => {
  beforeEach(() => {
    dispatch.mockClear();
    state = { tab: 'comparisons' };
  });
  afterEach(() => cleanup());

  it('renders ARIA tabs and switches tab on click/hash patch', async () => {
    const user = userEvent.setup();
    render(<SidePanel />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(2);
    expect(screen.queryByRole('tab', { name: 'Watchlist' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Comparisons' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'tab-comparisons');
    await user.click(screen.getByRole('tab', { name: 'Methods' }));
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { tab: 'methods' } });
  });

  it('arrow keys move between tabs', async () => {
    const user = userEvent.setup();
    render(<SidePanel />);
    screen.getByRole('tab', { name: 'Comparisons' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(dispatch).toHaveBeenCalledWith({ type: 'patch', patch: { tab: 'methods' } });
  });
});
