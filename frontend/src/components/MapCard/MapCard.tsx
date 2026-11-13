import { useEffect, useState, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, Circle, useMap, useMapEvents } from 'react-leaflet';
import type { LatLng, Map as LeafletMap } from 'leaflet';
import { useAppState } from '../../state/useAppState';
import { useCoverage } from '../../api/hooks';
import { parseEdges, areaKm2, validateEdges, insideRegion, cornersToEdges, validatePoint, pointAreaKm2, pointInRegion } from '../../lib/geo';
import { formatNumber, formatDate } from '../../lib/format';
import type { AppState } from '../../state/urlState';
import styles from './MapCard.module.css';

type BoxDraft = { n: string; s: string; e: string; w: string };
type PointDraft = { lat: string; lon: string; radius: string };
const emptyBox: BoxDraft = { n: '', s: '', e: '', w: '' };
const emptyPoint: PointDraft = { lat: '', lon: '', radius: '' };

function DrawController({ drawing, onStart, onMove, onEnd, onCancel }: {
  drawing: boolean; onStart: (p: LatLng) => void; onMove: (p: LatLng) => void; onEnd: (p: LatLng) => void; onCancel: () => void;
}) {
  const map = useMap();
  useEffect(() => {
    if (drawing) { map.dragging.disable(); map.getContainer().style.cursor = 'crosshair'; }
    else { map.dragging.enable(); map.getContainer().style.cursor = ''; }
    return () => { map.dragging.enable(); map.getContainer().style.cursor = ''; };
  }, [drawing, map]);
  useMapEvents({
    mousedown(e) { if (drawing) onStart(e.latlng); },
    mousemove(e) { if (drawing) onMove(e.latlng); },
    mouseup(e) { if (drawing) onEnd(e.latlng); },
  });
  useEffect(() => {
    if (!drawing) return;
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawing, onCancel]);
  return null;
}

function FitToBounds({ bounds }: { bounds: [[number, number], [number, number]] | null }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [20, 20] }); }, [bounds, map]);
  return null;
}

export default function MapCard() {
  const { state, dispatch } = useAppState();
  const { data: coverage } = useCoverage();
  const [mode, setMode] = useState<'box' | 'point'>('box');
  const [boxDraft, setBoxDraft] = useState<BoxDraft | null>(null);
  const [pointDraft, setPointDraft] = useState<PointDraft>(emptyPoint);
  const [dateDraft, setDateDraft] = useState<{ start: string; end: string } | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [basemap, setBasemap] = useState<'street' | 'satellite'>('street');
  const [map, setMap] = useState<LeafletMap | null>(null);
  const startRef = useRef<LatLng | null>(null);
  const [live, setLive] = useState<{ a: LatLng; b: LatLng } | null>(null);

  useEffect(() => {
    if (!state) return;
    if (!boxDraft) {
      if (state.area.kind === 'bbox') {
        const [w, s, e, n] = state.area.bbox;
        setBoxDraft({ n: String(n), s: String(s), e: String(e), w: String(w) });
        setMode('box');
      } else {
        const [lat, lon] = state.area.point;
        setPointDraft({ lat: String(lat), lon: String(lon), radius: String(state.area.radius_km) });
        setMode('point');
        setBoxDraft(emptyBox);
      }
    }
    if (!dateDraft) setDateDraft({ start: state.start, end: state.end });
  }, [state, boxDraft, dateDraft]);

  const b = boxDraft ?? emptyBox;
  const edges = parseEdges(b.n, b.s, b.e, b.w);
  const boxErr = validateEdges(b.n, b.s, b.e, b.w);
  const boxArea = edges ? areaKm2(edges.n, edges.s, edges.e, edges.w) : null;
  const pointErr = validatePoint(pointDraft.lat, pointDraft.lon, pointDraft.radius);
  const pLat = Number(pointDraft.lat), pLon = Number(pointDraft.lon), pRad = Number(pointDraft.radius);
  const pointValid = !pointErr && [pLat, pLon, pRad].every(Number.isFinite);
  const pointArea = pointValid ? pointAreaKm2(pRad) : null;

  const boxInRegion = edges && coverage ? coverage.regions.some((r) => insideRegion(edges, r.bbox as [number, number, number, number])) : false;
  const pointInside = pointValid && coverage ? coverage.regions.some((r) => pointInRegion(pLat, pLon, r.bbox as [number, number, number, number])) : false;

  const canAnalyzeArea = mode === 'box' ? (!!edges && !boxErr && !!boxInRegion) : (!!pointValid && !!pointInside);
  const areaErr = mode === 'box' ? boxErr : pointErr;
  const inRegion = mode === 'box' ? boxInRegion : pointInside;
  const area = mode === 'box' ? boxArea : pointArea;

  const region = coverage?.regions.find((r) => mode === 'box' ? (edges && insideRegion(edges, r.bbox as [number, number, number, number])) : (pointValid && pointInRegion(pLat, pLon, r.bbox as [number, number, number, number]))) ?? coverage?.regions[0];
  const covStart = region?.start ?? '';
  const covEnd = region?.latest_date ?? region?.end ?? '';
  const dd = dateDraft ?? { start: state?.start ?? '', end: state?.end ?? '' };
  let dateErr: string | null = null;
  if (!dd.start || !dd.end) dateErr = 'Choose a start date and an end date.';
  else if (dd.start > dd.end) dateErr = 'The start date must be before the end date.';
  else if ((covStart && dd.start < covStart) || (covEnd && dd.end > covEnd)) {
    dateErr = covStart && covEnd ? `Data covers ${formatDate(covStart)} to ${formatDate(covEnd)}.` : 'Date out of range.';
  }
  const canAnalyze = canAnalyzeArea && !dateErr;

  function iso(d: Date) { return d.toISOString().slice(0, 10); }
  function presetRange(name: string) {
    if (!covEnd) return null;
    const end = new Date(covEnd);
    if (name === '30') { const s = new Date(end); s.setDate(s.getDate() - 29); return { start: iso(s), end: covEnd }; }
    if (name === 'year') return { start: `${end.getUTCFullYear()}-01-01`, end: covEnd };
    if (name === '5') return { start: `${end.getUTCFullYear() - 4}-01-01`, end: covEnd };
    if (name === 'full') return covStart ? { start: covStart, end: covEnd } : null;
    return null;
  }
  const presetMatch = (name: string) => {
    const r = presetRange(name);
    return !!r && r.start === dd.start && r.end === dd.end;
  };

  function startDraw(p: LatLng) { startRef.current = p; setLive({ a: p, b: p }); }
  function moveDraw(p: LatLng) { if (startRef.current) setLive({ a: startRef.current, b: p }); }
  function endDraw(p: LatLng) {
    if (!startRef.current) return;
    const a = startRef.current;
    setBoxDraft(cornersToEdges(a.lat, a.lng, p.lat, p.lng));
    setDrawing(false); setLive(null); startRef.current = null;
  }

  let rectBounds: [[number, number], [number, number]] | null = null;
  if (mode === 'box') {
    if (live) rectBounds = [[Math.min(live.a.lat, live.b.lat), Math.min(live.a.lng, live.b.lng)], [Math.max(live.a.lat, live.b.lat), Math.max(live.a.lng, live.b.lng)]];
    else if (edges) rectBounds = [[edges.s, edges.w], [edges.n, edges.e]];
  }
  const circleBounds = mode === 'point' && pointValid ? [[pLat - pRad / 111, pLon - pRad / 111], [pLat + pRad / 111, pLon + pRad / 111]] as [[number, number], [number, number]] : null;
  const fitBounds = mode === 'box' ? rectBounds : circleBounds;

  const areaLabel = (() => {
    if (mode === 'point') return area ? `Selected area · ${formatNumber(area)} km²` : null;
    if (!edges || !coverage) return null;
    const sa = coverage.starter_areas.find((x) => x.bbox[0] === edges.w && x.bbox[1] === edges.s && x.bbox[2] === edges.e && x.bbox[3] === edges.n);
    if (sa) return `${sa.label} · ${formatNumber(area!)} km²`;
    const reg = coverage.regions.find((r) => insideRegion(edges, r.bbox as [number, number, number, number]));
    return `${reg?.label ?? 'Selected area'} · ${formatNumber(area!)} km²`;
  })();

  function jumpTo(name: string) {
    const sa = coverage?.starter_areas.find((x) => x.name === name);
    if (!sa) return;
    const [w, s, e, n] = sa.bbox;
    setMode('box'); setBoxDraft({ n: String(n), s: String(s), e: String(e), w: String(w) });
  }

  function analyze() {
    if (!canAnalyze) return;
    const patch: Partial<AppState> = { start: dd.start, end: dd.end };
    if (mode === 'box' && edges) patch.area = { kind: 'bbox', bbox: [edges.w, edges.s, edges.e, edges.n] };
    else if (mode === 'point' && pointValid) patch.area = { kind: 'point', point: [pLat, pLon], radius_km: pRad };
    dispatch({ type: 'patch', patch });
    if (map && fitBounds) map.fitBounds(fitBounds, { padding: [20, 20] });
  }

  return (
    <div className={styles.card}>
      <div className={styles.mapWrap}>
        <MapContainer center={[-16, -62]} zoom={5} zoomControl={false} ref={setMap} style={{ height: '100%', width: '100%' }} worldCopyJump={false} maxBounds={[[-90, -180], [90, 180]]} maxBoundsViscosity={1}>
          {basemap === 'street'
            ? <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            : <TileLayer attribution="Esri" url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />}
          {coverage?.regions.map((r) => (
            <Rectangle key={r.name} bounds={[[r.bbox[1], r.bbox[0]], [r.bbox[3], r.bbox[2]]]} pathOptions={{ color: '#6b6b6d', weight: 1, dashArray: '4 4', fill: false }} />
          ))}
          {mode === 'box' && rectBounds && <Rectangle bounds={rectBounds} pathOptions={{ color: '#0f0f0f', weight: 2, dashArray: '6 4', fill: false }} />}
          {mode === 'point' && pointValid && <Circle center={[pLat, pLon]} radius={pRad * 1000} pathOptions={{ color: '#0f0f0f', weight: 2, dashArray: '6 4', fill: false }} />}
          <FitToBounds bounds={fitBounds} />
          <DrawController drawing={drawing && mode === 'box'} onStart={startDraw} onMove={moveDraw} onEnd={endDraw} onCancel={() => { setDrawing(false); setLive(null); startRef.current = null; }} />
        </MapContainer>
        {areaLabel && fitBounds && <div className={styles.chip}>{areaLabel}</div>}
        <div className={styles.controls}>
          <div className={styles.controlGroup}>
            <button type="button" className={styles.controlBtn} aria-label="Zoom in" onClick={() => map?.zoomIn()}>+</button>
            <button type="button" className={styles.controlBtn} aria-label="Zoom out" onClick={() => map?.zoomOut()}>−</button>
          </div>
          <div className={styles.controlGroup}>
            <button type="button" className={styles.controlBtn} aria-pressed={drawing} aria-label="Draw area" disabled={mode === 'point'} onClick={() => setDrawing((x) => !x)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3"><rect x="4" y="4" width="16" height="16" rx="1" /></svg>
            </button>
            <button type="button" className={styles.controlBtn} aria-label="Delete area" onClick={() => { setBoxDraft(emptyBox); setPointDraft(emptyPoint); }}>✕</button>
          </div>
        </div>
        <div className={styles.basemap} role="group" aria-label="Basemap">
          <button type="button" className={styles.basemapBtn} aria-pressed={basemap === 'street'} onClick={() => setBasemap('street')}>Map</button>
          <button type="button" className={styles.basemapBtn} aria-pressed={basemap === 'satellite'} onClick={() => setBasemap('satellite')}>Satellite</button>
        </div>
        <div className={styles.jump}>
          <label className="visually-hidden" htmlFor="jump">Jump to</label>
          <select id="jump" className={styles.select} defaultValue="" onChange={(e) => jumpTo(e.target.value)}>
            <option value="">Jump to…</option>
            {coverage?.starter_areas.map((sa) => <option key={sa.name} value={sa.name}>{sa.label}</option>)}
          </select>
        </div>
        {drawing && <div className={styles.hint}>Drag on the map · Esc to cancel</div>}
      </div>
      <form className={styles.query} onSubmit={(e) => { e.preventDefault(); analyze(); }}>
        <div className={styles.row}>
          <div>
            <div className={styles.sizeLabel}>Area</div>
            <div className={styles.modeGroup} role="group" aria-label="Area mode">
              <button type="button" className={styles.modeBtn} aria-pressed={mode === 'box'} onClick={() => setMode('box')}>Box</button>
              <button type="button" className={styles.modeBtn} aria-pressed={mode === 'point'} onClick={() => setMode('point')}>Point + radius</button>
            </div>
          </div>
          {mode === 'box' ? (
            <>
              {(['n', 's', 'e', 'w'] as const).map((k) => {
                const label = k === 'n' ? 'North edge' : k === 's' ? 'South edge' : k === 'e' ? 'East edge' : 'West edge';
                return (
                  <label key={k} className={styles.label}>{label}
                    <input className={styles.input} inputMode="decimal" value={b[k]} aria-describedby={areaErr || (!inRegion && edges) ? 'area-err' : undefined} aria-invalid={!!areaErr}
                      onChange={(ev) => setBoxDraft((prev) => ({ ...(prev ?? emptyBox), [k]: ev.target.value }))} />
                  </label>
                );
              })}
            </>
          ) : (
            <>
              <label className={styles.label}>Latitude<input className={styles.input} inputMode="decimal" value={pointDraft.lat} aria-describedby={areaErr || (!inRegion && pointValid) ? 'area-err' : undefined} onChange={(e) => setPointDraft((p) => ({ ...p, lat: e.target.value }))} /></label>
              <label className={styles.label}>Longitude<input className={styles.input} inputMode="decimal" value={pointDraft.lon} aria-describedby={areaErr || (!inRegion && pointValid) ? 'area-err' : undefined} onChange={(e) => setPointDraft((p) => ({ ...p, lon: e.target.value }))} /></label>
              <label className={styles.label}>Radius (km)<input className={styles.input} inputMode="decimal" value={pointDraft.radius} aria-describedby={areaErr || (!inRegion && pointValid) ? 'area-err' : undefined} onChange={(e) => setPointDraft((p) => ({ ...p, radius: e.target.value }))} /></label>
            </>
          )}
          <div className={styles.size}>
            <div className={styles.sizeLabel}>Size</div>
            <div className={styles.sizeValue}>{area !== null ? `${formatNumber(area)} km²` : '—'}</div>
          </div>
        </div>
        {areaErr ? <div id="area-err" className={styles.error}>{areaErr}</div>
          : !inRegion && ((mode === 'box' && edges) || (mode === 'point' && pointValid)) ? <div id="area-err" className={styles.error}>This area is outside the covered regions.</div>
          : <div className={styles.helper}>Decimal degrees, with minus for south and west (18°S = −18). Drawing on the map fills these in.</div>}

        <div className={`${styles.row} ${styles.datesRow}`}>
          <div className={styles.sizeLabel}>Dates</div>
          <label className={styles.label}>Start<input className={styles.input} type="date" value={dd.start} min={covStart || undefined} max={covEnd || undefined} aria-describedby={dateErr ? 'date-err' : undefined} onChange={(e) => setDateDraft((p) => ({ ...(p ?? dd), start: e.target.value }))} /></label>
          <label className={styles.label}>End<input className={styles.input} type="date" value={dd.end} min={covStart || undefined} max={covEnd || undefined} aria-describedby={dateErr ? 'date-err' : undefined} onChange={(e) => setDateDraft((p) => ({ ...(p ?? dd), end: e.target.value }))} /></label>
          <div className={styles.modeGroup} role="group" aria-label="Date presets">
            {[
              ['30', 'Last 30 days'], ['year', 'This year'], ['5', 'Last 5 years'], ['full', 'Full record'],
            ].map(([k, label]) => (
              <button key={k} type="button" className={styles.modeBtn} aria-pressed={presetMatch(k)} onClick={() => { const r = presetRange(k); if (r) setDateDraft(r); }}>{label}</button>
            ))}
          </div>
          <button className={styles.analyze} type="submit" disabled={!canAnalyze} aria-describedby={dateErr ? 'date-err' : (areaErr || (!inRegion && ((mode === 'box' && edges) || (mode === 'point' && pointValid)))) ? 'area-err' : undefined}>Analyze this area →</button>
        </div>
        {dateErr ? <div id="date-err" className={styles.error}>{dateErr}</div> : null}
      </form>
    </div>
  );
}