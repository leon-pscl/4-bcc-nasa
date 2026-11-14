import { useMemo, useState } from 'react';
import { useAppState } from '../../state/useAppState';
import { useQueryParams, useHotspots } from '../../api/hooks';
import { buildAreaParams } from '../../api/params';
import styles from './HotspotTable.module.css';

const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];
function pad(n: number) { return String(n).padStart(2, '0'); }
function lastDay(y: number, m: number) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); } // m 1-12
function clipRange(focus: string, start: string, end: string) {
  const [ys, ms] = focus.split('-');
  const y = Number(ys), m = Number(ms);
  let s = `${y}-${pad(m)}-01`;
  let e = `${y}-${pad(m)}-${pad(lastDay(y, m))}`;
  if (s < start) s = start;
  if (e > end) e = end;
  return { start: s, end: e };
}

export default function HotspotTable() {
  const { state, dispatch } = useAppState();
  const { valid } = useQueryParams(state);
  const [page, setPage] = useState(1);
  const [showSensors, setShowSensors] = useState(false);

  const focus = state.focus;
  const range = useMemo(() => focus ? clipRange(focus, state.start, state.end) : { start: state.start, end: state.end }, [focus, state.start, state.end]);
  const params = useMemo(() => {
    if (!valid) return '';
    const p = buildAreaParams(state.area);
    p.set('start', range.start);
    p.set('end', range.end);
    if (state.cover) p.set('cover', state.cover);
    return p.toString();
  }, [valid, state.area, state.cover, range]);

  // reset page when query/focus changes
  const key = `${params}|${showSensors ? 1 : 0}`;
  const [lastKey, setLastKey] = useState(key);
  if (key !== lastKey) { setLastKey(key); setPage(1); }

  const { data, isLoading } = useHotspots(params, page, showSensors);

  if (!valid) return null;

  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 100;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const curPage = Math.min(page, pages);

  const headingRight = (() => {
    if (focus) {
      const [ys, ms] = focus.split('-');
      const label = `${MONTH_FULL[Number(ms) - 1]} ${ys}`;
      return <>{label} · {total.toLocaleString('en-US')} detections <button type="button" className={styles.linkBtn} onClick={() => dispatch({ type: 'patch', patch: { focus: undefined } })}>Show all dates</button></>;
    }
    return <>{total.toLocaleString('en-US')} detections</>;
  })();

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Hotspots in this search</h2>
        <div className={styles.count}>{headingRight}</div>
      </div>
      <div className={styles.controls}>
        <label className={styles.check}><input type="checkbox" checked={showSensors} onChange={(e) => { setShowSensors(e.target.checked); setPage(1); }} /> Show sensor details</label>
      </div>
      {isLoading ? <p className={styles.muted}>Loading hotspots…</p> : total === 0 ? <p className={styles.muted}>No hotspots in this area and date range.</p> : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr>
                <th>Date (local)</th><th>Time (UTC)</th><th className={styles.num}>Latitude</th><th className={styles.num}>Longitude</th><th>Confidence</th><th className={styles.num}>FRP (MW)</th><th>Day/Night</th>
                {showSensors && <><th>Sensor</th><th>Platform</th><th>Processing</th></>}
              </tr></thead>
              <tbody>
                {(data?.rows ?? []).map((r, i) => {
                  const t = r.acq_datetime_utc.includes('T') ? r.acq_datetime_utc.split('T')[1].slice(0,5) : r.acq_datetime_utc.slice(11,16);
                  return (
                    <tr key={i}>
                      <td>{r.date_local}</td><td>{t}</td>
                      <td className={styles.num}>{r.latitude.toFixed(4)}</td><td className={styles.num}>{r.longitude.toFixed(4)}</td>
                      <td>{r.confidence_class}</td><td className={styles.num}>{r.frp.toFixed(1)}</td><td>{r.daynight}</td>
                      {showSensors && <><td>{r.sensor ?? ''}</td><td>{r.platform ?? ''}</td><td>{r.processing ?? ''}</td></>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className={styles.pager}>
            <button type="button" className={styles.pageBtn} onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={curPage <= 1}>Previous</button>
            <span>Page {curPage} of {pages}</span>
            <button type="button" className={styles.pageBtn} onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={curPage >= pages}>Next</button>
          </div>
        </>
      )}
    </section>
  );
}
