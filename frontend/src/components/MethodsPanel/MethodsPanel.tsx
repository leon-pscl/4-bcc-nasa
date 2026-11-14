import { useAppState } from '../../state/useAppState';
import { useCoverage, useMethods, useQueryParams, useSeries } from '../../api/hooks';
import { insideRegion, pointInRegion } from '../../lib/geo';
import styles from './MethodsPanel.module.css';

function fmt(v: number, digits = 3) { return v.toFixed(digits); }
function fmtPct(v: number) { return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`; }

export default function MethodsPanel() {
  const { state } = useAppState();
  const { params } = useQueryParams(state);
  const { data: coverage } = useCoverage();
  const { data: series } = useSeries(params);
  let regionName = coverage?.regions[0]?.name ?? '';
  if (coverage) {
    if (state.area.kind === 'bbox') {
      const [w,s,e,n] = state.area.bbox;
      const edges = { n, s, e, w };
      regionName = coverage.regions.find((r) => insideRegion(edges, r.bbox as [number,number,number,number]))?.name ?? regionName;
    } else {
      const [lat, lon] = state.area.point;
      regionName = coverage.regions.find((r) => pointInRegion(lat, lon, r.bbox as [number,number,number,number]))?.name ?? regionName;
    }
  }
  const { data, isLoading } = useMethods(regionName);
  const typical = series?.validation?.typical_year_error_pct;

  if (isLoading) return <p className={styles.muted}>Loading methods…</p>;
  if (!data) return <p className={styles.muted}>No methods data available.</p>;

  const cal = data.calibration;
  const vcal = data.validation.calibration_years;
  const vval = data.validation.validation_years;
  const levels = Object.entries(cal.count_per_level || {}).map(([k, n]) => `${k.replace('_', ' ')}: ${n}`).join(' · ');

  return (
    <div className={styles.root}>
      <section className={styles.section}>
        <h3 className={styles.heading}>What one hotspot means</h3>
        <p className={styles.body}>One grid cell (0.05°, about 5.5 km across) with at least one fire detection on a given day. Counting cells instead of raw detections stops VIIRS&apos;s smaller pixels from inflating the numbers, and MODIS days are scaled so they count like VIIRS days.</p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Where the data comes from</h3>
        <div className={styles.timeline} aria-label="Data timeline">
          <div className={styles.segLeft}>MODIS Aqua × k</div>
          <div className={styles.segRight}>VIIRS S-NPP</div>
        </div>
        <div className={styles.timelineLabels}><span>Jan 2003</span><span>Feb 2012</span><span>Today</span></div>
        <p className={styles.body}>Active-fire hotspots come from NASA FIRMS. MODIS (Aqua, about 1 km pixels) gives the long history; VIIRS (S-NPP, 375 m) takes over from February 2012. On days with no VIIRS data, scaled MODIS fills the gap.</p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>How MODIS years were scaled</h3>
        <p className={styles.body}>For each 1° tile and month, k = VIIRS fire cell-days ÷ MODIS fire cell-days in the overlap period, with fallbacks to coarser levels when data is sparse.</p>
        <dl className={styles.dl}>
          <div><dt>Median k</dt><dd>{fmt(cal.k_median, 2)}</dd></div>
          <div><dt>Range of k</dt><dd>{fmt(cal.k_min, 2)}–{fmt(cal.k_max, 2)}</dd></div>
          <div><dt>Calibration level used</dt><dd>{levels || '—'}</dd></div>
        </dl>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Does the scaling hold up?</h3>
        <div className={styles.tiles}>
          <div className={styles.tile}><div className={styles.tileLabel}>r (calibration)</div><div className={styles.tileValue}>{fmt(vcal.metrics.pearson_r, 3)}</div></div>
          <div className={styles.tile}><div className={styles.tileLabel}>Bias (calibration)</div><div className={styles.tileValue}>{fmtPct(vcal.metrics.bias_pct)}</div></div>
          <div className={styles.tile}><div className={styles.tileLabel}>Median abs % error</div><div className={styles.tileValue}>{fmtPct(vcal.metrics.median_abs_pct_error)}</div></div>
        </div>
        <p className={styles.body}><strong>Calibration years:</strong> {vcal.years.join(', ')} — r {fmt(vcal.metrics.pearson_r,3)}, bias {fmtPct(vcal.metrics.bias_pct)}, median abs % error {fmtPct(vcal.metrics.median_abs_pct_error)}.</p>
        <p className={styles.body}><strong>Validation years:</strong> {vval.years.join(', ')} — r {fmt(vval.metrics.pearson_r,3)}, bias {fmtPct(vval.metrics.bias_pct)}, median abs % error {fmtPct(vval.metrics.median_abs_pct_error)}.</p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Limits and notes</h3>
        <p className={styles.body}>Scaling assumes the MODIS–VIIRS relationship in the overlap years holds for earlier years in each area. Before 2012, Terra fills Aqua-blind days (gap-fill) so MODIS-era coverage is as complete as possible.</p>
        <p className={styles.body}>Land cover comes from MCD12Q1, using the map from the year before each fire. VIIRS S-NPP ended 2 Nov 2026; NOAA-20/21 provide continuity after that.</p>
        <p className={styles.body}>Typical yearly error before 2012 for this area is about {typical != null ? `±${Math.round(typical)}%` : '±—'} (MODIS-estimate uncertainty).</p>
      </section>
    </div>
  );
}
