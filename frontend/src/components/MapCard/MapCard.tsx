import { useEffect, useMemo, useState, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import type { LatLng, Map as LeafletMap } from 'leaflet';
import { useAppState } from '../../state/useAppState';
import { useQueryParams, useMap as useMapData, useCalendar, useOutlook, useOutlookMap } from '../../api/hooks';
import { buildAreaParams } from '../../api/params';
import { parseEdges, areaKm2, validateEdges, insideRegion, cornersToEdges } from '../../lib/geo';
import { formatNumber, formatDate, formatLat, formatLon, formatDeg } from '../../lib/format';
import { COUNT_RAMP, countBins, countColor, CHANCE_BINS, chanceColor } from '../../lib/colors';
import { areaKey, type AppState, type AreaState } from '../../state/urlState';
import styles from './MapCard.module.css';

type BoxDraft = { n: string; s: string; e: string; w: string };
const emptyBox: BoxDraft = { n: '', s: '', e: '', w: '' };
const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function boundsFromArea(area: AreaState): [[number, number], [number, number]] | null {
  if (area.kind === 'bbox') { const [w, s, e, n] = area.bbox; return [[s, w], [n, e]]; }
  const [lat, lon] = area.point;
  const d = area.radius_km / 111;
  return [[lat - d, lon - d], [lat + d, lon + d]];
}

function DrawController({ drawing, onStart, onMove, onEnd, onAbort, onCancel }: {
  drawing: boolean; onStart: (p: LatLng) => void; onMove: (p: LatLng) => void; onEnd: (p?: LatLng) => void; onAbort: () => void; onCancel: () => void;
}) {
  const map = useMap();
  const pressRef = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    const c = map.getContainer();
    if (drawing) { map.dragging.disable(); map.doubleClickZoom.disable(); map.boxZoom.disable(); c.style.cursor = 'crosshair'; }
    else { map.dragging.enable(); map.doubleClickZoom.enable(); map.boxZoom.enable(); c.style.cursor = ''; }
    return () => { map.dragging.enable(); map.doubleClickZoom.enable(); map.boxZoom.enable(); c.style.cursor = ''; };
  }, [drawing, map]);
  useMapEvents({
    mousedown(e) { if (drawing) { pressRef.current = e.containerPoint; onStart(e.latlng); } },
    mousemove(e) { if (drawing && pressRef.current) onMove(e.latlng); },
    mouseup(e) {
      if (!drawing) return;
      const p = pressRef.current; pressRef.current = null;
      if (!p) return;
      if (Math.hypot(e.containerPoint.x - p.x, e.containerPoint.y - p.y) < 5) { onAbort(); return; }
      onEnd(e.latlng);
    },
  });
  useEffect(() => {
    if (!drawing) return;
    const onDocUp = () => { if (pressRef.current) { pressRef.current = null; onEnd(); } };
    document.addEventListener('mouseup', onDocUp);
    return () => document.removeEventListener('mouseup', onDocUp);
  }, [drawing, onEnd]);
  useEffect(() => {
    if (!drawing) return;
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') { pressRef.current = null; onCancel(); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawing, onCancel]);
  return null;
}

type EdgeLabelPos = { left: number; top: number };
const LABEL_W = 120;
const LABEL_H = 26;

function clamp(v: number, min: number, max: number) { return Math.min(Math.max(v, min), Math.max(min, max)); }

function EdgeLabels({ map, bounds }: { map: LeafletMap | null; bounds: [[number, number], [number, number]] | null }) {
  const [pos, setPos] = useState<{ n: EdgeLabelPos; s: EdgeLabelPos; e: EdgeLabelPos; w: EdgeLabelPos } | null>(null);
  useEffect(() => {
    if (!map || !bounds) { setPos(null); return; }
    const update = () => {
      const [[s, w], [n, e]] = bounds;
      const size = map.getSize();
      const cx = (w + e) / 2, cy = (n + s) / 2;
      const pN = map.latLngToContainerPoint([n, cx]);
      const pS = map.latLngToContainerPoint([s, cx]);
      const pW = map.latLngToContainerPoint([cy, w]);
      const pE = map.latLngToContainerPoint([cy, e]);
      setPos({
        n: { left: clamp(pN.x - LABEL_W / 2, 8, size.x - 8 - LABEL_W), top: clamp(pN.y - 6 - LABEL_H, 8, size.y - 8 - LABEL_H) },
        s: { left: clamp(pS.x - LABEL_W / 2, 8, size.x - 8 - LABEL_W), top: clamp(pS.y + 6, 8, size.y - 8 - LABEL_H) },
        w: { left: clamp(pW.x - 6 - LABEL_W, 8, size.x - 8 - LABEL_W), top: clamp(pW.y - LABEL_H / 2, 8, size.y - 8 - LABEL_H) },
        e: { left: clamp(pE.x + 6, 8, size.x - 8 - LABEL_W), top: clamp(pE.y - LABEL_H / 2, 8, size.y - 8 - LABEL_H) },
      });
    };
    update();
    map.on('move zoom resize', update);
    return () => { map.off('move zoom resize', update); };
  }, [bounds, map]);
  if (!pos || !bounds) return null;
  const [[s, w], [n, e]] = bounds;
  return (
    <>
      <div aria-hidden="true" className={styles.edgeLabel} style={pos.n}>North {formatDeg(n, 'lat')}</div>
      <div aria-hidden="true" className={styles.edgeLabel} style={pos.s}>South {formatDeg(s, 'lat')}</div>
      <div aria-hidden="true" className={styles.edgeLabel} style={pos.w}>West {formatDeg(w, 'lon')}</div>
      <div aria-hidden="true" className={styles.edgeLabel} style={pos.e}>East {formatDeg(e, 'lon')}</div>
    </>
  );
}

function DraftChip({ map, bounds, label, aboveLabel }: { map: LeafletMap | null; bounds: [[number, number], [number, number]] | null; label: string | null; aboveLabel?: boolean }) {
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const chipRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!map || !bounds || !label) { setPos(null); return; }
    const update = () => {
      const [[, w], [n, e]] = bounds;
      const size = map.getSize();
      const half = (chipRef.current?.offsetWidth ?? 200) / 2;
      const p = map.latLngToContainerPoint([n, (w + e) / 2]);
      setPos({ left: clamp(p.x, 8 + half, size.x - 8 - half), top: aboveLabel ? p.y - 38 : p.y - 6 });
    };
    update();
    map.on('move zoom resize', update);
    return () => { map.off('move zoom resize', update); };
  }, [bounds, label, map, aboveLabel]);
  if (!pos || !label) return null;
  return <div ref={chipRef} className={styles.chip} style={{ left: pos.left, top: pos.top, transform: 'translate(-50%, -100%)' }}>{label}</div>;
}

export default function MapCard() {
  const { state, dispatch } = useAppState();
  const { params, coverage } = useQueryParams(state);
  const monthParam = state.focus ?? undefined;
  const { data: mapData } = useMapData(params, monthParam);
  const { data: calendar } = useCalendar(params);
  const areaParams = state ? buildAreaParams(state.area) : '';
  const layer: 'history' | 'outlook' = state?.layer ?? 'history';
  const lead = state?.lead ?? 1;
  const outlookOn = layer === 'outlook';
  const { data: outlook } = useOutlook(areaParams, outlookOn);
  const { data: outlookMap } = useOutlookMap(areaParams, lead, outlookOn);
  const mode = 'box' as const;
  const [boxDraft, setBoxDraft] = useState<BoxDraft | null>(null);
  const [dateDraft, setDateDraft] = useState<{ start: string; end: string } | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [basemap, setBasemap] = useState<'street' | 'satellite'>('street');
  const [map, setMap] = useState<LeafletMap | null>(null);
  const startRef = useRef<LatLng | null>(null);
  const liveRef = useRef<{ a: LatLng; b: LatLng } | null>(null);
  const [live, setLiveState] = useState<{ a: LatLng; b: LatLng } | null>(null);
  const setLive = (v: { a: LatLng; b: LatLng } | null) => { liveRef.current = v; setLiveState(v); };

  // pan to the outlook cell picked in the Outlook tab ("Show on map")
  useEffect(() => {
    if (!map || !state?.cell) return;
    const [lat, lon] = state.cell;
    map.setView([lat, lon], Math.max(map.getZoom(), 8));
  }, [map, state?.cell]);

  useEffect(() => {
    if (!state) return;
    if (!boxDraft && state.area.kind === 'bbox') {
      const [w, s, e, n] = state.area.bbox;
      setBoxDraft({ n: String(n), s: String(s), e: String(e), w: String(w) });
    }
    if (!dateDraft) setDateDraft({ start: state.start, end: state.end });
  }, [state, boxDraft, dateDraft]);

  const b = boxDraft ?? emptyBox;
  const edges = parseEdges(b.n, b.s, b.e, b.w);
  const boxErr = validateEdges(b.n, b.s, b.e, b.w);
  const boxArea = edges ? areaKm2(edges.n, edges.s, edges.e, edges.w) : null;
  const boxInRegion = edges && coverage ? coverage.regions.some((r) => insideRegion(edges, r.bbox as [number, number, number, number])) : false;

  const canAnalyzeArea = !!edges && !boxErr && !!boxInRegion;
  const areaErr = boxErr;
  const inRegion = boxInRegion;
  const area = boxArea;

  const region = coverage?.regions.find((r) => edges && insideRegion(edges, r.bbox as [number, number, number, number])) ?? coverage?.regions[0];
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
  function endDraw(p?: LatLng) {
    const start = startRef.current;
    const target = p ?? liveRef.current?.b;
    if (!start || !target) return;
    setBoxDraft(cornersToEdges(start.lat, start.lng, target.lat, target.lng));
    setDrawing(false); setLive(null); startRef.current = null;
  }
  function abortDraw() { setLive(null); startRef.current = null; }

  const en = edges?.n ?? null, es = edges?.s ?? null, ee = edges?.e ?? null, ew = edges?.w ?? null;
  const rectBounds = useMemo((): [[number, number], [number, number]] | null => {
    if (mode !== 'box') return null;
    if (live) return [[Math.min(live.a.lat, live.b.lat), Math.min(live.a.lng, live.b.lng)], [Math.max(live.a.lat, live.b.lat), Math.max(live.a.lng, live.b.lng)]];
    if (en !== null && es !== null && ee !== null && ew !== null) return [[es, ew], [en, ee]];
    return null;
  }, [mode, live, en, es, ee, ew]);
  const circleBounds = null;
  const coverageBounds = useMemo((): [[number, number], [number, number]] | null => {
    if (!coverage?.regions?.length) return null;
    const rs = coverage.regions.map((r) => r.bbox);
    return [[Math.min(...rs.map((r) => r[1])), Math.min(...rs.map((r) => r[0]))], [Math.max(...rs.map((r) => r[3])), Math.max(...rs.map((r) => r[2]))]];
  }, [coverage]);

  const didInitialFit = useRef(false);
  useEffect(() => {
    if (didInitialFit.current || !map || !state) return;
    const target = boundsFromArea(state.area) ?? coverageBounds;
    if (!target) return;
    map.fitBounds(target, { padding: [20, 20] });
    didInitialFit.current = true;
  }, [map, state, coverageBounds]);

  const areaKeyValue = state ? areaKey(state.area) : '';
  const lastAnalyzeKey = useRef<string | null>(null);
  const prevAreaKey = useRef(areaKeyValue);
  useEffect(() => {
    if (prevAreaKey.current === areaKeyValue) return;
    prevAreaKey.current = areaKeyValue;
    if (lastAnalyzeKey.current === areaKeyValue) { lastAnalyzeKey.current = null; return; }
    if (!map || !state) return;
    const target = boundsFromArea(state.area);
    if (target) map.fitBounds(target, { padding: [20, 20] });
  }, [areaKeyValue, map, state]);

  const areaLabel = (() => {
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
    if (map) map.fitBounds([[s, w], [n, e]], { padding: [20, 20], maxZoom: 10 });
  }

  function analyze() {
    if (!canAnalyze) return;
    const patch: Partial<AppState> = { start: dd.start, end: dd.end };
    if (edges) patch.area = { kind: 'bbox', bbox: [edges.w, edges.s, edges.e, edges.n] };
    dispatch({ type: 'patch', patch });
    if (patch.area) lastAnalyzeKey.current = areaKey(patch.area);
    const target = mode === 'box' ? rectBounds : circleBounds;
    if (map && target) map.fitBounds(target, { padding: [20, 20], maxZoom: 10 });
  }

  const mapBins = useMemo(() => {
    if (!mapData?.cells?.length) return [];
    return countBins(mapData.cells.map((c) => c.value));
  }, [mapData]);

  const focus = state.focus;
  const focusCount = useMemo(() => {
    if (!focus || !calendar) return null;
    const [yStr, mStr] = focus.split('-');
    const yi = calendar.years.indexOf(Number(yStr));
    const mi = Number(mStr) - 1;
    if (yi < 0 || mi < 0) return null;
    const v = calendar.values[yi]?.[mi];
    if (v == null) return null;
    return v;
  }, [focus, calendar]);

  const footerText = (() => {
    if (focus) {
      const [yStr, mStr] = focus.split('-');
      const label = `${MONTH_FULL[Number(mStr) - 1]} ${yStr}`;
      const count = focusCount != null ? ` (${formatNumber(focusCount)} hotspots)` : '';
      return { label: `${label}${count}`, focused: true };
    }
    return { label: `the full record, ${state.start.slice(0,4)}–${state.end.slice(0,4)}`, focused: false };
  })();

  const draftShapeBounds = rectBounds;

  return (
    <div className={styles.card}>
      <div className={styles.mapWrap}>
        <MapContainer center={[0, 110]} zoom={4} zoomControl={false} ref={setMap} style={{ height: '100%', width: '100%' }} worldCopyJump={false} maxBounds={[[-90, -180], [90, 180]]} maxBoundsViscosity={1}>
          {basemap === 'street'
            ? <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            : <TileLayer attribution="Esri" url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />}
          {coverage?.regions.map((r) => (
            <Rectangle
              key={r.name}
              bounds={[[r.bbox[1], r.bbox[0]], [r.bbox[3], r.bbox[2]]]}
              interactive={!drawing}
              pathOptions={{ color: '#6b6b6d', weight: 1, dashArray: '4 4', fill: false }}
            >
              {!drawing && <Tooltip>{r.label}</Tooltip>}
            </Rectangle>
          ))}
          {!outlookOn && mapData?.cells.map((c, i) => {
            const g = mapData.grid_deg;
            const half = g / 2;
            const color = countColor(c.value, mapBins);
            return (
              <Rectangle key={`${c.lat}-${c.lon}-${i}`} bounds={[[c.lat - half, c.lon - half], [c.lat + half, c.lon + half]]}
                interactive={!drawing}
                pathOptions={{ color, weight: 0.5, fillColor: color, fillOpacity: 0.75 }}>
                {!drawing && <Popup>{`${formatNumber(c.value)} hotspots · ${formatLat(c.lat)}, ${formatLon(c.lon)}`}</Popup>}
              </Rectangle>
            );
          })}
          {outlookOn && outlookMap?.cells.map((c) => {
            const half = outlookMap.grid_deg / 2;
            const color = chanceColor(c.p_fire);
            const target = outlookMap.target;
            const mLabel = `${MONTH_FULL[target.month - 1]} ${target.year}`;
            return (
              <Rectangle key={`${c.lat}-${c.lon}`} bounds={[[c.lat - half, c.lon - half], [c.lat + half, c.lon + half]]}
                pathOptions={{ color, weight: 0.5, fillColor: color, fillOpacity: 0.75 }}>
                <Popup>{`${mLabel} · ${Math.round(c.p_fire * 100)}% chance of fire activity · about ${formatNumber(c.expected)} hotspots`}</Popup>
              </Rectangle>
            );
          })}
          {state?.cell && (
            <Rectangle bounds={[[state.cell[0] - 0.075, state.cell[1] - 0.075], [state.cell[0] + 0.075, state.cell[1] + 0.075]]}
              pathOptions={{ color: '#0f0f0f', weight: 2.5, fillColor: '#0f0f0f', fillOpacity: 0.12, dashArray: '6 4' }} />
          )}
          {rectBounds && <Rectangle bounds={rectBounds} pathOptions={{ color: '#0f0f0f', weight: 2, dashArray: '6 4', fill: false }} />}
          <DrawController drawing={drawing} onStart={startDraw} onMove={moveDraw} onEnd={endDraw} onAbort={abortDraw} onCancel={() => { setDrawing(false); setLive(null); startRef.current = null; }} />
        </MapContainer>
        <EdgeLabels map={map} bounds={rectBounds} />
        <DraftChip map={map} bounds={draftShapeBounds} label={areaLabel} aboveLabel={!!rectBounds} />
        <div className={styles.controls}>
          <div className={styles.controlGroup}>
            <button type="button" className={styles.controlBtn} aria-label="Zoom in" onClick={() => map?.zoomIn()}>+</button>
            <button type="button" className={styles.controlBtn} aria-label="Zoom out" onClick={() => map?.zoomOut()}>−</button>
          </div>
          <div className={styles.controlGroup}>
            <div className={styles.drawWrapper}>
              <button
                type="button"
                className={styles.controlBtn}
                aria-pressed={drawing}
                aria-label="Draw area"
                disabled={mode === 'point'}
                onClick={() => setDrawing((x) => !x)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3"><rect x="4" y="4" width="16" height="16" rx="1" /></svg>
              </button>
              {drawing && <div className={styles.hint}>Drag on the map · Esc to cancel</div>}
            </div>
            <button type="button" className={styles.controlBtn} aria-label="Delete area" onClick={() => { setBoxDraft(emptyBox); }}>✕</button>
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
      </div>

      <div className={styles.footer}>
        <div className={styles.footerLeft}>
          {!outlookOn ? (
            <span>Map shows <strong>{footerText.label}</strong>{footerText.focused ? <> <button type="button" className={styles.linkBtn} onClick={() => dispatch({ type: 'patch', patch: { focus: undefined } })}>Show full record</button></> : null}</span>
          ) : (
            <span>Outlook (experimental) · <strong>{outlookMap ? `${MONTH_FULL[outlookMap.target.month - 1]} ${outlookMap.target.year}` : '…'}</strong> — chance of fire activity</span>
          )}
          <div className={styles.layerSwitch} role="group" aria-label="Map layer">
            <button type="button" className={styles.layerBtn} aria-pressed={!outlookOn} onClick={() => dispatch({ type: 'patch', patch: { layer: 'history' } })}>History</button>
            <button type="button" className={styles.layerBtn} aria-pressed={outlookOn} onClick={() => dispatch({ type: 'patch', patch: { layer: 'outlook' } })}>Outlook</button>
          </div>
        </div>
        {!outlookOn ? (
          <div className={styles.legend}><span>Hotspots per cell</span>{COUNT_RAMP.map((c) => <span key={c} className={styles.legendSwatch} style={{ background: c }} />)}<span>fewer to more</span></div>
        ) : (
          <div className={styles.legend}><span>Chance of fire</span>{CHANCE_BINS.map((b) => <span key={b.label} className={styles.legendSwatch} style={{ background: b.color }} title={b.label} />)}<span>rare to likely</span></div>
        )}
        {outlookOn && (
          <div className={styles.layerSwitch} role="group" aria-label="Outlook month">
            {(outlook?.months ?? []).map((m) => (
              <button key={m.lead} type="button" className={styles.layerBtn} aria-pressed={lead === m.lead} onClick={() => dispatch({ type: 'patch', patch: { lead: m.lead as 1 | 2 | 3 } })}>{MONTH_SHORT[m.month - 1]}</button>
            ))}
          </div>
        )}
        {outlookOn && state?.cover && state.cover !== 'all' ? <div className={styles.agg}>The outlook covers all fire types; the land-type filter doesn't apply to it.</div> : null}
        {outlookOn ? <div className={styles.agg}>15 km cells. Sea, lakes, barren land and ice are left out. &ldquo;fire activity&rdquo; = at least 1 hotspot in the cell that month.</div> : null}
        {!outlookOn && mapData?.aggregated_to != null ? <div className={styles.agg}>Shown on a coarser {mapData.aggregated_to}° grid to keep the map fast.</div> : null}
      </div>

      <form className={styles.query} onSubmit={(e) => { e.preventDefault(); analyze(); }}>
        <div className={styles.row}>
          <div>
            <div className={styles.sizeLabel}>Area</div>
          </div>
          <div className={styles.compass}>
              {([
                ['n', 'North edge', styles.compassN],
                ['w', 'West edge', styles.compassW],
                ['e', 'East edge', styles.compassE],
                ['s', 'South edge', styles.compassS],
              ] as const).map(([k, label, area]) => (
                <label key={k} className={`${styles.label} ${area}`}>{label}
                  <input className={styles.input} inputMode="decimal" value={b[k]} aria-describedby={areaErr || (!inRegion && edges) ? 'area-err' : undefined} aria-invalid={!!areaErr}
                    onChange={(ev) => setBoxDraft((prev) => ({ ...(prev ?? emptyBox), [k]: ev.target.value }))} />
                </label>
              ))}
              <div className={styles.compassC} aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3"><rect x="4" y="4" width="16" height="16" rx="1" /></svg>
              </div>
            </div>
          <div className={styles.size}>
            <div className={styles.sizeLabel}>Size</div>
            <div className={styles.sizeValue}>{area !== null ? `${formatNumber(area)} km²` : '—'}</div>
          </div>
        </div>
        {areaErr ? <div id="area-err" className={styles.error}>{areaErr}</div>
          : !inRegion && edges ? <div id="area-err" className={styles.error}>This area is outside the covered regions.</div>
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
          <button className={styles.analyze} type="submit" disabled={!canAnalyze} aria-describedby={dateErr ? 'date-err' : (areaErr || (!inRegion && edges)) ? 'area-err' : undefined}>Analyze this area →</button>
        </div>
        {dateErr ? <div id="date-err" className={styles.error}>{dateErr}</div> : null}
      </form>
    </div>
  );
}