import { useState } from 'react';
import { useAppState } from '../../state/useAppState';
import { useQueryParams } from '../../api/hooks';
import { formatDate } from '../../lib/format';
import styles from './Downloads.module.css';

function isMockMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('mock') === '1' || import.meta.env.VITE_USE_MOCKS === 'true';
}

export default function Downloads() {
  const { state } = useAppState();
  const { params, valid, coverage } = useQueryParams(state);
  const [allSensors, setAllSensors] = useState(false);
  const mock = isMockMode();

  if (!valid) return null;

  const name = (() => {
    if (state.area.kind === 'bbox' && coverage) {
      const sa = coverage.starter_areas.find((x) => x.bbox.every((v, i) => v === state.area.bbox[i]));
      if (sa) return sa.label;
      const reg = coverage.regions.find((r) => state.area.bbox[0] >= r.bbox[0] && state.area.bbox[2] <= r.bbox[2] && state.area.bbox[1] >= r.bbox[1] && state.area.bbox[3] <= r.bbox[3]);
      return reg?.label ?? 'Selected area';
    }
    return 'Selected area';
  })();

  const q = params;
  const hsHref = `/api/hotspots.csv?${q}&all_sensors=${allSensors ? 1 : 0}`;
  const calHref = `/api/calendar.csv?${q}`;
  const pngHref = `/api/calendar.png?${q}`;
  const disabled = mock || !q;

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Download this search</h2>
        <div className={styles.meta}>{name} · {formatDate(state.start)} to {formatDate(state.end)}</div>
      </div>
      <div className={styles.row}>
        <a className={`${styles.btn} ${styles.primary} ${disabled ? styles.disabled : ''}`} href={hsHref} download aria-disabled={disabled} tabIndex={disabled ? -1 : 0} onClick={(e) => { if (disabled) e.preventDefault(); }}>Hotspots CSV</a>
        <label className={styles.check}><input type="checkbox" checked={allSensors} onChange={(e) => setAllSensors(e.target.checked)} disabled={disabled} /> Include all sensors</label>
        <a className={`${styles.btn} ${disabled ? styles.disabled : ''}`} href={calHref} download aria-disabled={disabled} tabIndex={disabled ? -1 : 0} onClick={(e) => { if (disabled) e.preventDefault(); }}>Calendar CSV</a>
        <a className={`${styles.btn} ${disabled ? styles.disabled : ''}`} href={pngHref} download aria-disabled={disabled} tabIndex={disabled ? -1 : 0} onClick={(e) => { if (disabled) e.preventDefault(); }}>Calendar image (PNG)</a>
      </div>
      {mock ? <p className={styles.note}>Downloads need the live API.</p> : null}
      <p className={styles.note}>Hotspots CSV: one row per detection, with date, UTC time, latitude, longitude, confidence, fire radiative power, day/night and sensor. By default it holds only the detections behind the calendar; tick &quot;Include all sensors&quot; for every MODIS and VIIRS detection in the area.</p>
    </section>
  );
}
