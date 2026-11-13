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
    if (initialHashEmpty && coverage) {
      const sa = coverage.starter_areas[0];
      const region = coverage.regions.find((r) => r.name === sa.region);
      const area: AreaState = { kind: 'bbox', bbox: sa.bbox as [number, number, number, number] };
      dispatch({ type: 'set', state: {
        area,
        start: region?.start ?? coverage.regions[0].start,
        end: region?.latest_date ?? coverage.regions[0].latest_date,
        view: 'count',
        tab: 'comparisons',
      }});
      return;
    }
    if (!initialHashEmpty) {
      const parsed = parseHash(window.location.hash);
      dispatch({ type: 'set', state: {
        area: parsed.area ?? { kind: 'bbox', bbox: coverage?.starter_areas[0]?.bbox as [number, number, number, number] ?? [0,0,0,0] },
        start: parsed.start ?? coverage?.regions[0]?.start ?? '',
        end: parsed.end ?? coverage?.regions[0]?.latest_date ?? '',
        view: parsed.view ?? 'count',
        focus: parsed.focus,
        tab: parsed.tab ?? 'comparisons',
      }});
    }
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