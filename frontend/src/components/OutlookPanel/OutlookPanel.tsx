import { useMemo } from 'react';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend, type ChartOptions,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { useAppState } from '../../state/useAppState';
import { useOutlook, useQueryParams } from '../../api/hooks';
import { buildAreaParams } from '../../api/params';
import { formatNumber } from '../../lib/format';
import type { AreaState } from '../../state/urlState';
import styles from './OutlookPanel.module.css';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);
ChartJS.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function coverageThrough(latest: string): string {
  // "from data through 14 Nov 2026" — latest_data_date is the last date in the record
  const [y, m, d] = latest.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

export default function OutlookPanel() {
  const { state, dispatch } = useAppState();
  const { valid } = useQueryParams(state);
  const areaParams = state ? buildAreaParams(state.area as AreaState) : '';
  const { data: outlook, isLoading, isError } = useOutlook(areaParams);
  const lead = state?.lead ?? 1;

  const medianArr = useMemo(() => outlook?.season.normal_median ?? [], [outlook]);
  const peakIdx = medianArr.length ? medianArr.indexOf(Math.max(...medianArr)) : -1;

  const chartData = useMemo(() => ({
    labels: MONTHS,
    datasets: [{
      label: 'Typical month (median)',
      data: medianArr,
      backgroundColor: medianArr.map((_, i) => (i === peakIdx ? '#0f0f0f' : '#9a9a9c')),
      borderWidth: 0,
    }],
  }), [medianArr, peakIdx]);

  const chartOpts: ChartOptions<'bar'> = useMemo(() => ({
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${formatNumber(Number(c.parsed.y))} hotspots` } } },
    scales: {
      x: { ticks: { font: { family: "'IBM Plex Sans', system-ui, sans-serif", size: 10 } } },
      y: { ticks: { font: { family: "'IBM Plex Sans', system-ui, sans-serif", size: 10 } } },
    },
  }), []);

  if (!valid) return <p className={styles.muted}>Choose a valid area to see the outlook.</p>;
  if (state?.cover && state.cover !== 'all') return <p className={styles.muted}>The outlook covers all fire types; the land-type filter doesn't apply to it.</p>;
  if (isLoading) return <p className={styles.muted}>Loading the outlook.</p>;
  if (isError || !outlook) return <p className={styles.muted}>The outlook is not available for this area.</p>;

  const months = [...outlook.months].sort((a, b) => a.lead - b.lead);
  const selected = months.find((m) => m.lead === lead) ?? months[0];
  const topCells = outlook.top_cells.filter((c) => c.lead === lead).slice(0, 10);
  const fmt2 = (x: number) => (Math.round((Math.abs(x) + 1e-9) * 100) / 100).toFixed(2);
  const cellLabel = (c: { lat: number; lon: number }) =>
    `${fmt2(c.lat)}°${c.lat >= 0 ? 'N' : 'S'}, ${fmt2(c.lon)}°${c.lon >= 0 ? 'E' : 'W'}`;
  const monthName = MONTH_FULL[(selected.month - 1)];
  const skill = outlook.skill;

  return (
    <>
      <section className={styles.section}>
        <h2 className={styles.heading}>What&apos;s coming?</h2>
        <p className={styles.mutedLine}>
          Outlook (experimental) from data through {coverageThrough(outlook.latest_data_date)}.
          Based on past fire patterns, not a weather forecast.
        </p>
        <div className={styles.months}>
          {months.map((m) => {
            const inProgress = m.observed_so_far != null;
            return (
              <div key={m.lead} className={styles.card}>
                <div className={styles.label}>{MONTH_FULL[m.month - 1]} {m.year}{inProgress ? ' · in progress' : ''}</div>
                <div className={styles.bigRow}>
                  <span className={styles.big}>{formatNumber(m.expected)}</span>
                  <span className={styles.unit}>{outlook.unit === 'Hotspots (harmonized)' ? 'hotspots' : outlook.unit}</span>
                </div>
                {m.typical_range ? <div className={styles.typical}>typical range {formatNumber(m.typical_range[0])}–{formatNumber(m.typical_range[1])}</div> : null}
                {m.normal_median != null ? <div className={styles.typicalMedian}>Typical {MONTH_FULL[m.month - 1]} (median): <strong>{formatNumber(m.normal_median)}</strong></div> : null}
                {inProgress && m.observed_so_far ? (
                  <div className={styles.soFar}>So far (1–{m.observed_so_far.through_day} {MONTHS[m.month - 1]}): <strong>{formatNumber(m.observed_so_far.value)}</strong></div>
                ) : null}
              </div>
            );
          })}
        </div>
        <p className={styles.foot}>
          Typical range: middle half of the 2003–2025 complete years. Issued {outlook.issued}; targets {months.map((m) => `${MONTHS[m.month - 1]} ${m.year}`).join(', ')}.
        </p>
      </section>

      <section className={styles.section}>
        <div className={styles.whereHead}>
          <h2 className={styles.heading}>Where?</h2>
          <div className={styles.switch} role="group" aria-label="Month">
            {months.map((m) => (
              <button
                key={m.lead}
                type="button"
                className={styles.switchBtn}
                aria-pressed={lead === m.lead}
                onClick={() => dispatch({ type: 'patch', patch: { lead: m.lead as 1 | 2 | 3 } })}
              >
                {MONTHS[m.month - 1]}
              </button>
            ))}
          </div>
        </div>
        <ol className={styles.topList} data-testid="top-cells">
          {topCells.map((c, i) => (
            <li key={`${c.lead}-${c.lat}-${c.lon}`} className={styles.topRow}>
              <span className={styles.topRank}>{i + 1}</span>
              <span className={styles.topLoc}>{cellLabel(c)}</span>
              <span className={styles.topChance}>{Math.round(c.p_fire * 100)}% chance</span>
              <span className={styles.topHot}>about {formatNumber(c.expected)} hotspots</span>
              <button
                type="button"
                className={styles.showMap}
                aria-label={`Show cell ${cellLabel(c)} on the map`}
                onClick={() => dispatch({
                  type: 'patch',
                  patch: { layer: 'outlook', lead: c.lead as 1 | 2 | 3, cell: [c.lat, c.lon] },
                })}
              >
                Show on map
              </button>
            </li>
          ))}
        </ol>
        <p className={styles.foot}>
          The 10 most likely cells for {monthName} {selected.year}.
        </p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.heading}>When does this area burn?</h2>
        <div className={styles.canvas120}>
          <Bar data={chartData} options={chartOpts} role="img"
               aria-label={`Typical month by month; peak is ${MONTHS[peakIdx]} with ${formatNumber(Math.max(...medianArr))} hotspots`} />
        </div>
        <p className={styles.sentence}>Busiest months: <strong>{outlook.season.busiest_months.map((m) => MONTHS[m - 1]).join(', ')}</strong></p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.heading}>How reliable is this?</h2>
        <div className={styles.stats}>
          <div className={styles.stat}>
            <div className={styles.statLabel}>Fire caught by the top 10% of cells</div>
            <div className={styles.statValue}>{skill?.top10_capture_pct != null ? `${skill.top10_capture_pct.toFixed(0)}%` : '—'}</div>
          </div>
          <div className={styles.stat}>
            <div className={styles.statLabel}>Tested on</div>
            <div className={styles.statValue}>{skill ? `${Math.min(...skill.test_years)}–${Math.max(...skill.test_years)}` : '—'}</div>
          </div>
        </div>
        <button type="button" className={styles.methodsLink} onClick={() => dispatch({ type: 'patch', patch: { tab: 'methods' } })}>
          How the outlook works
        </button>
        <p className={styles.foot}>
          The outlook learns from where and when fires happened before. It is an experimental
          climatology, not a forecast with weather: it can miss new fire zones entirely.
        </p>
      </section>
    </>
  );
}

