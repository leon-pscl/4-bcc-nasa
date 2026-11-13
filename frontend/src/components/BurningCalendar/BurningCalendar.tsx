import { useMemo } from 'react';
import { useAppState } from '../../state/useAppState';
import { useCalendar, useCoverage, useSummary } from '../../api/hooks';
import { COUNT_RAMP, ANOMALY_BINS, countColor, anomalyColor, textOn, quantileBins, binLabels } from '../../lib/colors';
import { formatNumber, formatSignedPct, formatDate, formatLat, formatLon } from '../../lib/format';
import type { AppState } from '../../state/urlState';
import styles from './BurningCalendar.module.css';

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function buildParams(state: Pick<AppState, 'area' | 'start' | 'end'>) {
  const p = new URLSearchParams();
  if (state.area.kind === 'bbox') p.set('bbox', state.area.bbox.join(','));
  else { p.set('point', state.area.point.join(',')); p.set('radius_km', String(state.area.radius_km)); }
  p.set('start', state.start); p.set('end', state.end);
  return p.toString();
}

export default function BurningCalendar() {
  const { state, dispatch } = useAppState();
  const params = buildParams(state);
  const { data, isLoading, error } = useCalendar(params);
  const { data: summary } = useSummary(params);
  const { data: coverage } = useCoverage();

  const bins = useMemo(() => {
    if (!data) return [];
    const vals = data.values.flat().filter((v): v is number => v !== null && v > 0);
    return quantileBins(vals, 7);
  }, [data]);

  if (isLoading) return <section className={styles.card}>Loading calendar…</section>;
  if (error) return <section className={styles.card}>Couldn’t load calendar.</section>;
  if (!data) return null;

  const view = state.view;
  const rows = data.years.map((y, i) => {
    let values = data.values[i];
    let total = data.annual_totals[i];
    if (data.partial && y === data.partial.year) {
      values = values.map((v, mi) => (mi > data.partial!.month - 1 ? null : v));
      total = values.reduce<number>((a, v) => a + (v ?? 0), 0);
    }
    return { year: y, values, anomaly: data.anomaly[i], anomalyPct: data.anomaly_pct[i], total };
  }).reverse();
  const completeMax = Math.max(1, ...rows.filter((r) => !data.partial_years.includes(r.year)).map((r) => r.total));
  const medianTotal = (() => {
    const baseline = data.years.map((y, i) => ({ y, t: data.annual_totals[i] }))
      .filter((x) => data.baseline_years.includes(x.y) && !data.partial_years.includes(x.y))
      .map((x) => x.t);
    if (!baseline.length) return 0;
    const s = [...baseline].sort((a,b)=>a-b); const m = Math.floor(s.length/2);
    return s.length % 2 ? s[m] : (s[m-1]+s[m])/2;
  })();

  const subtitle = (() => {
    const q = data.query;
    let name = 'Selected area';
    if (q.bbox && coverage) {
      const sa = coverage.starter_areas.find((x) => x.bbox.every((v, i) => v === q.bbox![i]));
      if (sa) name = sa.label;
      else {
        const reg = coverage.regions.find((r) => q.bbox![0] >= r.bbox[0] && q.bbox![2] <= r.bbox[2] && q.bbox![1] >= r.bbox[1] && q.bbox![3] <= r.bbox[3]);
        name = reg?.label ?? 'Selected area';
      }
    }
    if (q.bbox) {
      const [w, s, e, n] = q.bbox;
      const coords = `${formatLat(s)}–${formatLat(n)}, ${formatLon(w)}–${formatLon(e)}`;
      const area = q.area_km2 != null ? `${formatNumber(q.area_km2)} km²` : '';
      return `Hotspots (harmonized) per month · ${name} · ${coords} · ${area} · ${formatDate(q.start)} – ${formatDate(q.end)}`;
    }
    return `Hotspots (harmonized) per month · ${name} · ${formatDate(q.start)} – ${formatDate(q.end)}`;
  })();

  function pctMag(n: number) { return `${Math.abs(Math.round(n))}%`; }
  function cellLabel(year: number, monthIdx: number, value: number | null, pct: number | null, isPartial: boolean) {
    const m = MONTH_FULL[monthIdx];
    if (value === null) return `${m} ${year}: outside range`;
    const count = `${formatNumber(value)} hotspots`;
    if (isPartial && data.partial) {
      if (summary?.current_month) {
        const p = summary.current_month.pct_vs_median;
        const cmp = p === 0 ? 'at the median' : `${pctMag(p)} ${p > 0 ? 'above' : 'below'} the median`;
        return `${m} ${year}, days 1 to ${data.partial.through_day} so far: ${formatNumber(value)} hotspots, ${cmp} for the same days`;
      }
      return `${m} ${year}, days 1 to ${data.partial.through_day} so far: ${formatNumber(value)} hotspots, no median to compare with`;
    }
    if (pct === null) return `${m} ${year}: ${count}, no median to compare with`;
    if (pct === 0) return `${m} ${year}: ${count}, at the median`;
    const dir = pct > 0 ? 'above' : 'below';
    return `${m} ${year}: ${count}, ${pctMag(pct)} ${dir} the median`;
  }

  function cellText(value: number | null, pct: number | null, isPartial: boolean) {
    if (value === null) return '–';
    if (view === 'count') return formatNumber(value);
    if (isPartial && summary?.current_month) return formatSignedPct(summary.current_month.pct_vs_median);
    if (pct === null) return 'n/a';
    return formatSignedPct(pct);
  }

  function cellBg(value: number | null, pct: number | null) {
    if (value === null) return 'var(--surface)';
    if (view === 'count') return countColor(value, bins);
    return anomalyColor(pct);
  }

  function toggleFocus(year: number, monthIdx: number) {
    const f = `${year}-${String(monthIdx + 1).padStart(2, '0')}`;
    dispatch({ type: 'patch', patch: { focus: state.focus === f ? undefined : f } });
  }

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Burning calendar</h2>
          <div className={styles.subtitle}>{subtitle}</div>
        </div>
        <div className={styles.viewToggle} role="group" aria-label="View">
          <button type="button" className={styles.viewBtn} aria-pressed={view === 'count'} onClick={() => dispatch({ type: 'patch', patch: { view: 'count' } })}>Count</button>
          <button type="button" className={styles.viewBtn} aria-pressed={view === 'anomaly'} onClick={() => dispatch({ type: 'patch', patch: { view: 'anomaly' } })}>Anomaly vs median</button>
        </div>
      </div>

      <div className={styles.legend}>
        {view === 'count' ? (
          <>
            <span>Hotspots per month</span>
            <span><span className={styles.swatch} style={{ background: '#f0f0f0' }} />0</span>
            {COUNT_RAMP.map((c, i) => <span key={c}><span className={styles.swatch} style={{ background: c }} />{binLabels(bins)[i] ?? ''}</span>)}
          </>
        ) : (
          <>
            <span>Difference from the monthly median</span>
            {ANOMALY_BINS.map((b) => <span key={b.label}><span className={styles.swatch} style={{ background: b.color }} />{b.label}</span>)}
          </>
        )}
      </div>

      {data.baseline_warning ? <div className={styles.warning}>{data.baseline_warning}</div> : null}
      {data.coverage_warning ? <div className={styles.warning}>{data.coverage_warning}</div> : null}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className="visually-hidden">Hotspots per month (columns) and year (rows)</caption>
          <thead>
            <tr>
              <th scope="col" className={styles.yearHead}>Year</th>
              {MONTHS.map((m) => <th key={m} scope="col">{m}</th>)}
              <th scope="col">Year total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.year}>
                <th scope="row" className={styles.yearCell}>
                  {row.year}
                  {data.partial_years.includes(row.year) ? <span className={styles.partialTag}>PARTIAL</span> : null}
                </th>
                {row.values.map((v, mi) => {
                  const pct = row.anomalyPct[mi];
                  const isPartial = !!data.partial && data.partial.year === row.year && data.partial.month === mi + 1;
                  const f = `${row.year}-${String(mi + 1).padStart(2, '0')}`;
                  const focused = state.focus === f;
                  if (v === null) return <td key={mi} className={styles.cellEmpty}>–</td>;
                  const bg = cellBg(v, pct);
                  return (
                    <td key={mi}>
                      <button
                        type="button"
                        className={`${styles.cellBtn} ${isPartial ? styles.partialCell : ''} ${focused ? styles.focused : ''}`}
                        style={{ background: bg, color: textOn(bg === '#f0f0f0' ? '#f0f0f0' : bg) }}
                        aria-label={cellLabel(row.year, mi, v, pct, isPartial)}
                        onClick={() => toggleFocus(row.year, mi)}
                      >
                        {cellText(v, pct, isPartial)}{isPartial ? <span className={styles.soFar}>SO FAR</span> : null}
                      </button>
                    </td>
                  );
                })}
                <td className={styles.totalCell}>
                  <div className={styles.totalTrack}>
                    <div className={`${styles.totalBar} ${data.partial_years.includes(row.year) ? styles.totalBarPartial : ''}`} style={{ width: `${Math.min(100, (row.total / completeMax) * 100)}%` }} />
                    <div className={styles.totalText}>{formatNumber(row.total)}</div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className={styles.medianRow}>
              <th scope="row" className={styles.yearCell}>MEDIAN<br /><span style={{ fontSize: 11, fontWeight: 400 }}>{data.baseline_years[0]}–{data.baseline_years[data.baseline_years.length - 1]}</span></th>
              {data.monthly_median.map((m, i) => <td key={i} style={{ textAlign: 'center' }}>{formatNumber(m)}</td>)}
              <td style={{ textAlign: 'right', paddingRight: 6 }}>{formatNumber(medianTotal)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className={styles.footnote}>One hotspot = one fire cell-day in VIIRS-equivalent terms (see Methods). The outlined cell is the current month so far, compared with the median of the same days in past years. Hatched totals are partial years. Select a cell to show that month on the map.</div>
    </section>
  );
}