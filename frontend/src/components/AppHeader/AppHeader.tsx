import { useCoverage } from '../../api/hooks';
import { formatDate } from '../../lib/format';
import styles from './AppHeader.module.css';

const RAMP = ['#ffffb2','#fed976','#feb24c','#fd8d3c','#fc4e2a','#e31a1c','#b10026'];

export default function AppHeader() {
  const { data } = useCoverage();
  const through = data?.regions?.[0]?.latest_date;
  async function copy() {
    const live = document.getElementById('live-region');
    try {
      await navigator.clipboard?.writeText(window.location.href);
      if (live) live.textContent = 'Link copied';
    } catch {
      if (live) live.textContent = 'Couldn\'t copy link';
    }
  }
  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <span aria-hidden className={styles.mark}>
          {RAMP.map((c, i) => <span key={i} className={styles.bar} style={{ height: 8 + i * 4, background: c }} />)}
        </span>
        <div>
          <div className={styles.title}>Burning Calendar</div>
          <div className={styles.subtitle}>Harmonized MODIS + VIIRS fire hotspots, 2003 to today</div>
        </div>
      </div>
      <div className={styles.meta}>
        <span>{through ? `Data through ${formatDate(through)}` : null}</span>
        <button className={styles.copy} onClick={copy}>Copy link to this view</button>
      </div>
    </header>
  );
}