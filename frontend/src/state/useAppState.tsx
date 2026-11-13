import { createContext, useContext, useEffect, useReducer, type ReactNode } from 'react';
import { parseHash, toHash, type AppState } from './urlState';

type Action =
  | { type: 'set'; state: AppState }
  | { type: 'patch'; patch: Partial<AppState> };

function reducer(state: AppState, action: Action): AppState {
  if (action.type === 'set') return action.state;
  return { ...state, ...action.patch };
}

const defaultState: AppState = {
  area: { kind: 'bbox', bbox: [110.7, -3.6, 115.9, 0.8] },
  start: '2003-01-01',
  end: '2026-11-12',
  view: 'count',
  tab: 'comparisons',
};

interface Ctx { state: AppState; dispatch: (a: Action) => void; }
const AppStateContext = createContext<Ctx | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => {
    const parsed = parseHash(window.location.hash);
    return { ...defaultState, ...parsed };
  });

  useEffect(() => {
    const onHash = () => {
      const parsed = parseHash(window.location.hash);
      dispatch({ type: 'patch', patch: parsed });
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    const newHash = toHash(state);
    if (window.location.hash !== newHash) window.location.hash = newHash;
  }, [state]);

  return <AppStateContext.Provider value={{ state, dispatch }}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}