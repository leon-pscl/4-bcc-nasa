import { createContext, useContext, useEffect, useReducer, useState, type ReactNode } from 'react';
import { useCoverage } from '../api/hooks';
import { parseHash, toHash, type AppState, type AreaState } from './urlState';

type Action =
  | { type: 'set'; state: AppState }
  | { type: 'patch'; patch: Partial<AppState> };

function reducer(state: AppState | null, action: Action): AppState | null {
  if (action.type === 'set') return action.state;
  if (!state) return state;
  return { ...state, ...action.patch };
}

interface Ctx { state: AppState | null; dispatch: (a: Action) => void; }
const AppStateContext = createContext<Ctx | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [initialHashEmpty] = useState(() => window.location.hash === '' || window.location.hash === '#');
  const { data: coverage } = useCoverage();
  const [state, dispatch] = useReducer(reducer, null);

  useEffect(() => {
    if (state) return;
    if (!coverage) return;
    const sa = coverage.starter_areas[0];
    const region = coverage.regions.find((r) => r.name === sa.region) ?? coverage.regions[0];
    const defaultArea: AreaState = { kind: 'bbox', bbox: sa.bbox as [number, number, number, number] };
    const defaults = {
      area: defaultArea,
      start: region.start,
      end: region.latest_date,
      view: 'count' as const,
      tab: 'comparisons' as const,
    };

    if (initialHashEmpty) {
      dispatch({ type: 'set', state: defaults });
      return;
    }

    const parsed = parseHash(window.location.hash);
    dispatch({ type: 'set', state: {
      area: parsed.area ?? defaults.area,
      start: parsed.start ?? defaults.start,
      end: parsed.end ?? defaults.end,
      view: parsed.view ?? defaults.view,
      focus: parsed.focus,
      tab: parsed.tab ?? defaults.tab,
    }});
  }, [coverage, state, initialHashEmpty]);

  useEffect(() => {
    if (!state) return;
    const onHash = () => {
      const parsed = parseHash(window.location.hash);
      dispatch({ type: 'patch', patch: parsed });
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [state]);

  useEffect(() => {
    if (!state) return;
    const newHash = toHash(state as AppState);
    if (window.location.hash !== newHash) window.location.hash = newHash;
  }, [state]);

  if (!state) return null;
  return <AppStateContext.Provider value={{ state: state as AppState, dispatch }}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}