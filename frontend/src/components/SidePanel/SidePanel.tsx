import { useRef, type KeyboardEvent } from 'react';
import { useAppState } from '../../state/useAppState';
import ComparisonsPanel from '../ComparisonsPanel/ComparisonsPanel';
import MethodsPanel from '../MethodsPanel/MethodsPanel';
import styles from './SidePanel.module.css';

const TABS = [
  { id: 'comparisons', label: 'Comparisons' },
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'methods', label: 'Methods' },
] as const;

export default function SidePanel() {
  const { state, dispatch } = useAppState();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (e: KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length : (i - 1 + TABS.length) % TABS.length;
    dispatch({ type: 'patch', patch: { tab: TABS[next].id } });
    refs.current[next]?.focus();
  };

  return (
    <section className={styles.card} aria-label="Side panel">
      <div role="tablist" aria-label="Side panel tabs" className={styles.tablist}>
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => { refs.current[i] = el; }}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={state.tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={state.tab === t.id ? 0 : -1}
            className={styles.tab}
            onClick={() => dispatch({ type: 'patch', patch: { tab: t.id } })}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`panel-${state.tab}`}
        aria-labelledby={`tab-${state.tab}`}
        className={styles.panel}
      >
        {state.tab === 'comparisons' && <ComparisonsPanel />}
        {state.tab === 'watchlist' && <p className={styles.placeholder}>Watchlist coming in 6i.</p>}
        {state.tab === 'methods' && <MethodsPanel />}
      </div>
    </section>
  );
}
