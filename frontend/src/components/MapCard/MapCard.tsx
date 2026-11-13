import { useEffect, useState, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, useMap, useMapEvents } from 'react-leaflet';
import type { LatLng, Map as LeafletMap } from 'leaflet';
import { useAppState } from '../../state/useAppState';
import { useCoverage } from '../../api/hooks';
import { parseEdges, areaKm2, wrapLon, round4, validateEdges, insideRegion } from '../../lib/geo';
import { formatNumber } from '../../lib/format';
import styles from './MapCard.module.css';

type Draft = { n: string; s: string; e: string; w: string };
const empty: Draft = { n: '', s: '', e: '', w: '', };

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

function FitToArea({ edges }: { edges: { n: number; s: number; e: number; w: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (!edges) return;
    map.fitBounds([[edges.s, edges.w], [edges.n, edges.e]], { padding: [20, 20] });
  }, [edges, map]);
  return null;
}

export default function MapCard() {
  const { state, dispatch } = useAppState();
  const { data: coverage } = useCoverage();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [basemap, setBasemap] = useState<'street' | 'satellite'>('street');
  const [map, setMap] = useState<LeafletMap | null>(null);
  const startRef = useRef<LatLng | null>(null);
  const [live, setLive] = useState<{ a: LatLng; b: LatLng } | null>(null);

  useEffect(() => {
    if (!state || draft) return;
    if (state.area.kind === 'bbox') {
      const [w, s, e, n] = state.area.bbox;
      setDraft({ n: String(n), s: String(s), e: String(e), w: String(w) });
    }
  }, [state, draft]);

  const d = draft ?? { n: '', s: '', e: '', w: '' };
  const edges = parseEdges(d.n, d.s, d.e, d.w);
  const err = validateEdges(d.n, d.s, d.e, d.w);
  const area = edges ? areaKm2(edges.n, edges.s, edges.e, edges.w) : null;
  const inRegion = edges && coverage ? coverage.regions.some((r) => insideRegion(edges, r.bbox as [number, number, number, number])) : false;
  const canAnalyze = !!edges && !err && !!inRegion;

  function startDraw(p: LatLng) { startRef.current = p; setLive({ a: p, b: p }); }
  function moveDraw(p: LatLng) { if (startRef.current) setLive({ a: startRef.current, b: p }); }
  function endDraw(p: LatLng) {
    if (!startRef.current) return;
    const a = startRef.current, b = p;
    setDraft({
      n: String(round4(Math.max(a.lat, b.lat))),
      s: String(round4(Math.min(a.lat, b.lat))),
      e: String(round4(wrapLon(Math.max(a.lng, b.lng)))),
      w: String(round4(wrapLon(Math.min(a.lng, b.lng)))),
    });
    setDrawing(false); setLive(null); startRef.current = null;
  }

  let rectBounds: [[number, number], [number, number]] | null = null;
  if (live) rectBounds = [[Math.min(live.a.lat, live.b.lat), Math.min(live.a.lng, live.b.lng)], [Math.max(live.a.lat, live.b.lat), Math.max(live.a.lng, live.b.lng)]];
  else if (edges) rectBounds = [[edges.s, edges.w], [edges.n, edges.e]];

  function jumpTo(name: string) {
    const sa = coverage?.starter_areas.find((x) => x.name === name);
    if (!sa) return;
    const [w, s, e, n] = sa.bbox;
    setDraft({ n: String(n), s: String(s), e: String(e), w: String(w) });
  }

  function analyze() {
    if (!edges) return;
    dispatch({ type: 'patch', patch: { area: { kind: 'bbox', bbox: [edges.w, edges.s, edges.e, edges.n] } } });
    setDrawing(false);
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
          {rectBounds && <Rectangle bounds={rectBounds} pathOptions={{ color: '#0f0f0f', weight: 2, dashArray: '6 4', fill: false }} />}
          <FitToArea edges={edges} />
          <DrawController drawing={drawing} onStart={startDraw} onMove={moveDraw} onEnd={endDraw} onCancel={() => { setDrawing(false); setLive(null); startRef.current = null; }} />
        </MapContainer>
        <div className={styles.controls}>
          <div className={styles.controlGroup}>
            <button className={styles.controlBtn} aria-label="Zoom in" disabled={map ? map.getZoom() >= map.getMaxZoom() : false} onClick={() => map?.zoomIn()}>+</button>
            <button className={styles.controlBtn} aria-label="Zoom out" disabled={map ? map.getZoom() <= map.getMinZoom() : false} onClick={() => map?.zoomOut()}>−</button>
          </div>
          <div className={styles.controlGroup}>
            <button className={styles.controlBtn} aria-pressed={drawing} aria-label="Draw area" onClick={() => setDrawing((x) => !x)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3"><rect x="4" y="4" width="16" height="16" rx="1" /></svg>
            </button>
            <button className={styles.controlBtn} aria-label="Delete area" disabled={!draft || (!d.n && !d.s && !d.e && !d.w)} onClick={() => setDraft(empty)}>✕</button>
          </div>
        </div>
        <div className={styles.basemap} role="group" aria-label="Basemap">
          <button className={styles.basemapBtn} aria-pressed={basemap === 'street'} onClick={() => setBasemap('street')}>Map</button>
          <button className={styles.basemapBtn} aria-pressed={basemap === 'satellite'} onClick={() => setBasemap('satellite')}>Satellite</button>
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
          {(['n', 's', 'e', 'w'] as const).map((k) => {
            const label = k === 'n' ? 'North edge' : k === 's' ? 'South edge' : k === 'e' ? 'East edge' : 'West edge';
            return (
              <label key={k} className={styles.label}>{label}
                <input className={styles.input} inputMode="decimal" value={d[k]} aria-describedby={err ? 'area-err' : undefined} aria-invalid={!!err}
                  onChange={(ev) => setDraft((prev) => ({ ...(prev ?? empty), [k]: ev.target.value }))} />
              </label>
            );
          })}
          <div className={styles.size}>
            <div className={styles.sizeLabel}>Size</div>
            <div className={styles.sizeValue}>{area !== null ? `${formatNumber(area)} km²` : '—'}</div>
          </div>
          <button className={styles.analyze} type="submit" disabled={!canAnalyze} aria-describedby={err ? 'area-err' : undefined}>Analyze this area →</button>
        </div>
        {err ? <div id="area-err" className={styles.error}>{err}</div>
          : !inRegion && edges ? <div id="area-err" className={styles.error}>This area is outside the covered regions.</div>
          : <div className={styles.helper}>Decimal degrees, with minus for south and west (18°S = −18). Drawing on the map fills these in.</div>}
      </form>
    </div>
  );
}