import { useAppState } from '../../state/useAppState';
import type { Cover } from '../../state/urlState';
import styles from './CoverControl.module.css';

export const OPTIONS: { id: Cover; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'forest', label: 'Forest' },
  { id: 'farmland', label: 'Farmland' },
  { id: 'other', label: 'Other land' },
];

export default function CoverControl() {
  const { state, dispatch } = useAppState();
  return (
    <div className={styles.wrap}>
      <span className={styles.label}>Fire type</span>
      <div className={styles.group} role="group" aria-label="Fire type">
        {OPTIONS.map((o) => (
          <button key={o.id} type="button" className={styles.btn} aria-pressed={state.cover === o.id} onClick={() => dispatch({ type: 'patch', patch: { cover: o.id } })}>{o.label}</button>
        ))}
      </div>
    </div>
  );
}
