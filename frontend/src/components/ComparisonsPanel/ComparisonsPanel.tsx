import { useMemo, useRef } from 'react';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Tooltip, Legend,
  type ChartOptions,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import { useAppState } from '../../state/useAppState';
import { useCalendar, useCoverage, useSummary } from '../../api/hooks';
import { formatNumber } from '../../lib/format';
import type { AreaState } from '../../state/urlState';
import styles from './ComparisonsPanel.module.css';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Tooltip, Legend);

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function buildParams(state: { area: AreaState; start: string; end: string }) {
  const p = new URLSearchParams();
  if (state.area.kind === 'bbox') p.set('bbox', state.area.bbox.join(','));
  else { p.set('point', state.area.point.join(',')); p.set('radius_km', String(state.area.radius_km)); }
  p.set('start', state.start); p.set('end', state.end);
  return p.toString();
}

function downloadPng(chart: ChartJS | null, name: string) {
  if (!chart) return;
  const a = document.createElement('a');
  a.href = chart.toBase64Image();
  a.download = name;
  a.click();
}

function fileBase(state: { area: AreaState; start: string; end: string }, kind: string) {
  const a = state.area.kind === 'bbox' ? state.area.bbox.join('_') : `${state.area.point.join('_')}_r${state.area.radius_km}`;
  return `${kind}_${a}_${state.start}_${state.end}.png`;
}

export default function ComparisonsPanel() {
  const { state } = useAppState();
  const params = useMemo(() => buildParams(state), [state]);
  const { data: summary } = useSummary(params);
  const { data: calendar } = useCalendar(params);
  const { data: coverage } = useCoverage();
  const monthRef = useRef<ChartJS<'line'> | null>(null);
  const yearRef = useRef<ChartJS<'bar'> | null>(null);

  if (!summary || !calendar) return <p className={styles.muted}>Loading comparisons.</p>;

  const cm = summary.current_month;
  const region = coverage?.regions.find((r) => state.area.kind === 'bbox' && state.area.bbox[0] >= r.bbox[0] && state.area.bbox[2] <= r.bbox[2] && state.area.bbox[1] >= r.bbox[1] && state.area.bbox[3] <= r.bbox[3]);
  const regionLabel = region?.label ?? 'area';

  const badge = cm ? (cm.pct_vs_median > 0 ? `↑ ${Math.round(cm.pct_vs_median)}% above the median` : cm.pct_vs_median < 0 ? `↓ ${Math.abs(Math.round(cm.pct_vs_median))}% below the median` : 'At the median') : '';
  const badgeClass = cm ? (cm.pct_vs_median > 0 ? styles.badgeUp : cm.pct_vs_median < 0 ? styles.badgeDown : styles.badgeEven) : '';
  const barMax = cm ? Math.max(cm.value, cm.median_same_span, 1) : 1;

  const focusYear = state.focus ? Number(state.focus.slice(0, 4)) : (cm?.year ?? calendar.years[calendar.years.length - 1]);
  const focusIdx = calendar.years.indexOf(focusYear);
  const focusVals = focusIdx >= 0 ? calendar.values[focusIdx] : null;
  const partial = calendar.partial;
  const focusSeries = focusVals ? focusVals.map((v, i) => {
    if (partial && focusYear === partial.year && i >= partial.month) return null;
    return v ?? 0;
  }) : null;

  const busiest = calendar.monthly_median.map((v, i) => ({ i, v })).sort((a,b)=>b.v-a.v).slice(0,3).map(x=>MONTHS[x.i]).join(', ');

  const monthlyData = {
    labels: MONTHS,
    datasets: [
      { label: 'P75', data: calendar.monthly_p75, borderColor: 'transparent', backgroundColor: 'rgba(107,107,109,0.25)', pointRadius: 0, fill: '+1' },
      { label: 'P25', data: calendar.monthly_p25, borderColor: 'transparent', pointRadius: 0, fill: false },
      { label: 'Median', data: calendar.monthly_median, borderColor: '#0f0f0f', backgroundColor: '#0f0f0f', pointRadius: 0, fill: false, tension: 0.2 },
      ...(focusSeries ? [{ label: String(focusYear), data: focusSeries, borderColor: '#e31a1c', backgroundColor: '#e31a1c', pointRadius: 0, fill: false, tension: 0.2, spanGaps: false }] : []),
    ],
  };

  const hatch = (() => {
    const c = document.createElement('canvas'); c.width = 6; c.height = 6;
    const ctx = c.getContext('2d'); if (!ctx) return '#6b6b6d';
    ctx.strokeStyle = '#6b6b6d'; ctx.beginPath(); ctx.moveTo(0,6); ctx.lineTo(6,0); ctx.stroke();
    return ctx.createPattern(c, 'repeat') ?? '#6b6b6d';
  })();

  const yearColors = calendar.years.map((y) => {
    if (calendar.partial_years.includes(y)) return hatch as string | CanvasPattern;
    const peak = summary.peak_year?.year === y;
    return peak ? '#0f0f0f' : '#6b6b6d';
  });

  const yearlyData = {
    labels: calendar.years.map((y) => String(y)),
    datasets: [{ label: 'Annual total', data: calendar.annual_totals, backgroundColor: yearColors, borderWidth: 0 }],
  };

  const yearOpts: ChartOptions<'bar'> = {
    responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { callback: (_v, i) => (i === 0 || i === calendar.years.length - 1) ? (calendar.partial_years.includes(calendar.years[i]) ? `${calendar.years[i]} (partial)` : String(calendar.years[i])) : '', maxRotation: 0, autoSkip: false, font: { family: 'IBM Plex Sans', size: 11 } } },
      y: { ticks: { font: { family: 'IBM Plex Sans', size: 11 } } },
    },
  };
  const monthOpts: ChartOptions<'line'> = {
    responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
    scales: { x: { ticks: { font: { family: 'IBM Plex Sans', size: 11 } } }, y: { ticks: { font: { family: 'IBM Plex Sans', size: 11 } } } },
  };

  const topYears = calendar.years.map((y, i) => ({ y, v: calendar.annual_totals[i] }))
    .filter((x) => !calendar.partial_years.includes(x.y)).sort((a,b)=>b.v-a.v).slice(0,3);

  const focusLabel = partial && focusYear === partial.year ? `${focusYear} (Jan–${MONTHS[partial.month - 1]})` : String(focusYear);

  return (
    <>
      <section className={styles.section}>
        <h3 className={styles.heading}>How does this month compare?</h3>
        <div className={styles.card}>
          {cm ? (
            <>
              <div className={styles.label}>{MONTH_FULL[cm.month - 1]} {cm.year}, days 1-{cm.through_day}</div>
              <div className={styles.bigRow}><span className={styles.big}>{formatNumber(cm.value)}</span><span className={styles.unit}>hotspots (harmonized)</span></div>
              <div className={`${styles.badge} ${badgeClass}`}>{badge}</div>
              <div className={styles.bars} role="img" aria-label={`This year ${Math.round(cm.value)} hotspots, median ${Math.round(cm.median_same_span)} for the same days`}>
                <div className={styles.barRow}><span>This year</span><div className={styles.track}><div className={styles.fill} style={{ width: `${(cm.value/barMax)*100}%`, background: '#e31a1c' }} /></div><span>{formatNumber(cm.value)}</span></div>
                <div className={styles.barRow}><span>Median</span><div className={styles.track}><div className={styles.fill} style={{ width: `${(cm.median_same_span/barMax)*100}%`, background: 'var(--ink)' }} /></div><span>{formatNumber(cm.median_same_span)}</span></div>
              </div>
              <div className={styles.foot}>Median of the same days ({MONTHS[cm.month - 1]} 1-{cm.through_day}) in {calendar.baseline_years[0]}-{calendar.baseline_years[calendar.baseline_years.length - 1]}. Whole months would make a month in progress look low.</div>
            </>
          ) : (
            <p className={styles.muted}>The selected dates don't include the current month. Pick a range that ends on the latest data date to compare.</p>
          )}
        </div>
        <div className={styles.stats}>
          <div className={styles.stat}><div className={styles.statLabel}>Total in range</div><div className={styles.statValue}>{formatNumber(summary.total)}</div></div>
          <div className={styles.stat}><div className={styles.statLabel}>Peak year</div><div className={styles.statValue}>{summary.peak_year ? `${summary.peak_year.year}` : '–'}</div></div>
          <div className={styles.stat}><div className={styles.statLabel}>Peak month</div><div className={styles.statValue}>{summary.peak_month ? `${MONTHS[summary.peak_month.month - 1]} ${summary.peak_month.year}` : '–'}</div></div>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>When in the year does it burn?</h3>
        <div className={styles.chartHead}><span /><button className={styles.pngBtn} onClick={() => downloadPng(monthRef.current, fileBase(state, 'monthly_pattern'))}>PNG</button></div>
        <div className={styles.canvas180}><Line ref={monthRef} data={monthlyData as never} options={monthOpts} aria-label={`Monthly pattern for ${regionLabel}, median and middle half with ${focusLabel}`} role="img" /></div>
        <div className={styles.legendHtml}>
          <span className={styles.legendItem}><span className={`${styles.swatch} ${styles.swatchMedian}`} /> Median</span>
          <span className={styles.legendItem}><span className={`${styles.swatch} ${styles.swatchBand}`} /> Middle half of years</span>
          <span className={styles.legendItem}><span className={`${styles.swatch} ${styles.swatchYear}`} /> {focusLabel}</span>
        </div>
        <p className={styles.sentence}>Busiest months: <strong>{busiest}</strong></p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Which years burned most?</h3>
        <div className={styles.chartHead}><span /><button className={styles.pngBtn} onClick={() => downloadPng(yearRef.current, fileBase(state, 'yearly_totals'))}>PNG</button></div>
        <div className={styles.canvas120}><Bar ref={yearRef} data={yearlyData as never} options={yearOpts} aria-label={`Yearly totals ${calendar.years[0]} to ${calendar.years[calendar.years.length - 1]}; highest complete year ${summary.peak_year?.year ?? ''} with ${summary.peak_year ? formatNumber(summary.peak_year.value) : ''} hotspots`} role="img" /></div>
        <div className={styles.topTitle}>Top years (complete years only)</div>
        <ol className={styles.topList}>
          {topYears.map((t, i) => <li key={t.y} className={styles.topRow}><span>{i + 1}</span><span>{t.y}</span><span>{formatNumber(t.v)}</span></li>)}
        </ol>
      </section>
    </>
  );
}
