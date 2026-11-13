import { useEffect, useState, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, useMap, useMapEvents } from 'react-leaflet';
import type { LatLng } from 'leaflet';
import { parseEdges, areaKm2, wrapLon, round4 } from '../../lib/geo';

type Draft = { n: string; s: string; e: string; w: string };

const empty: Draft = { n: '', s: '', e: '', w: '' };

// Custom draw controller: disables panning while drawing, captures mousedown/move/up.
function DrawController({
  drawing,
  onStart,
  onMove,
  onEnd,
  onCancel,
}: {
  drawing: boolean;
  onStart: (p: LatLng) => void;
  onMove: (p: LatLng) => void;
  onEnd: (p: LatLng) => void;
  onCancel: () => void;
}) {
  const map = useMap();
  useEffect(() => {
    if (drawing) {
      map.dragging.disable();
      map.getContainer().style.cursor = 'crosshair';
    } else {
      map.dragging.enable();
      map.getContainer().style.cursor = '';
    }
    return () => {
      map.dragging.enable();
      map.getContainer().style.cursor = '';
    };
  }, [drawing, map]);

  useMapEvents({
    mousedown(e) {
      if (!drawing) return;
      onStart(e.latlng);
    },
    mousemove(e) {
      if (!drawing) return;
      onMove(e.latlng);
    },
    mouseup(e) {
      if (!drawing) return;
      onEnd(e.latlng);
    },
  });

  useEffect(() => {
    if (!drawing) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawing, onCancel]);

  return null;
}

export default function MapCard() {
  const [draft, setDraft] = useState<Draft>(empty);
  const [drawing, setDrawing] = useState(false);
  const startRef = useRef<LatLng | null>(null);
  const liveRef = useRef<LatLng | null>(null);
  const [live, setLive] = useState<{ a: LatLng; b: LatLng } | null>(null);

  const edges = parseEdges(draft.n, draft.s, draft.e, draft.w);
  const area = edges ? areaKm2(edges.n, edges.s, edges.e, edges.w) : null;

  function startDraw(p: LatLng) {
    startRef.current = p;
    liveRef.current = p;
    setLive({ a: p, b: p });
  }
  function moveDraw(p: LatLng) {
    liveRef.current = p;
    if (startRef.current) setLive({ a: startRef.current, b: p });
  }
  function endDraw(p: LatLng) {
    if (!startRef.current) return;
    const a = startRef.current;
    const b = p;
    // bounds not needed; compute from corners
    // compute draft from two corners
    const n = Math.max(a.lat, b.lat);
    const s = Math.min(a.lat, b.lat);
    const e = wrapLon(Math.max(a.lng, b.lng)); // naive; wrap handled in toDraft? sort then wrap
    const w = wrapLon(Math.min(a.lng, b.lng));
    setDraft({
      n: String(round4(n)),
      s: String(round4(s)),
      e: String(round4(e)),
      w: String(round4(w)),
    });
    setDrawing(false);
    setLive(null);
    startRef.current = null;
  }

  function updateField(key: keyof Draft, val: string) {
    setDraft((d) => ({ ...d, [key]: val }));
  }

  // rectangle bounds from draft or live
  let rectBounds: [[number, number], [number, number]] | null = null;
  if (live) {
    const n = Math.max(live.a.lat, live.b.lat);
    const s = Math.min(live.a.lat, live.b.lat);
    const e = Math.max(live.a.lng, live.b.lng);
    const w = Math.min(live.a.lng, live.b.lng);
    rectBounds = [[s, w], [n, e]];
  } else if (edges) {
    rectBounds = [[edges.s, edges.w], [edges.n, edges.e]];
  }

  return (
    <div style={{ border: '1px solid #959596', borderRadius: 6, overflow: 'hidden', background: '#fff' }}>
      <div style={{ position: 'relative', aspectRatio: '2 / 1', minHeight: 280 }}>
        <MapContainer center={[ -16, -62 ]} zoom={5} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {rectBounds && <Rectangle bounds={rectBounds} pathOptions={{ color: '#0f0f0f', weight: 2, dashArray: '6 4', fill: false }} />}
          <DrawController
            drawing={drawing}
            onStart={startDraw}
            onMove={moveDraw}
            onEnd={endDraw}
            onCancel={() => { setDrawing(false); setLive(null); startRef.current = null; }}
          />
        </MapContainer>
        <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', gap: 6 }}>
          <button
            aria-pressed={drawing}
            aria-label="Draw area"
            title="Draw area"
            onClick={() => setDrawing((d) => !d)}
            style={{ width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', background: drawing ? '#0f0f0f' : '#fff', color: drawing ? '#fff' : '#0f0f0f', border: '1px solid #0f0f0f', borderRadius: 4, cursor: 'pointer' }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3">
              <rect x="4" y="4" width="16" height="16" rx="1" />
            </svg>
          </button>
          <button
            aria-label="Delete area"
            title="Delete area"
            onClick={() => { setDraft(empty); setLive(null); startRef.current = null; setDrawing(false); }}
            disabled={!draft.n && !draft.s && !draft.e && !draft.w}
            style={{ width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', color: '#0f0f0f', border: '1px solid #959596', borderRadius: 4, cursor: 'pointer', opacity: (!draft.n && !draft.s && !draft.e && !draft.w) ? 0.4 : 1 }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        {drawing && (
          <div style={{ position: 'absolute', top: 8, left: 104, height: 44, display: 'flex', alignItems: 'center', padding: '0 12px', background: '#fff', border: '1px solid #0f0f0f', borderRadius: 4, fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>
            Drag on the map · Esc to cancel
          </div>
        )}
      </div>

      <div style={{ padding: 16, borderTop: '1px solid #959596' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {(['n','s','e','w'] as const).map((k) => {
            const label = k === 'n' ? 'North edge' : k === 's' ? 'South edge' : k === 'e' ? 'East edge' : 'West edge';
            return (
              <label key={k} style={{ display: 'flex', flexDirection: 'column', fontSize: 11, fontFamily: 'ui-monospace, monospace', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6b6b6d' }}>
                {label}
                <input
                  inputMode="decimal"
                  value={draft[k]}
                  onChange={(ev) => updateField(k, ev.target.value)}
                  style={{ width: 104, height: 44, padding: '0 8px', border: '1px solid #959596', borderRadius: 4, fontFamily: 'inherit', fontSize: 14, color: '#0f0f0f', background: '#fff' }}
                />
              </label>
            );
          })}
          <div style={{ marginLeft: 8, fontFamily: 'ui-monospace, monospace' }}>
            <div style={{ fontSize: 11, color: '#6b6b6d', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Size</div>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{area !== null ? area.toLocaleString('en-US', { maximumFractionDigits: 0 }) + ' km²' : '—'}</div>
          </div>
        </div>
        {!edges && (draft.n || draft.s || draft.e || draft.w) && (
          <div style={{ marginTop: 8, color: '#b2182b', fontSize: 13 }}>
            Check the edges: north/south within ±90, east/west within ±180, south below north, west left of east, area ≤ 500,000 km².
          </div>
        )}
        {edges && area !== null && area > 500000 && (
          <div style={{ marginTop: 8, color: '#b2182b', fontSize: 13 }}>Larger than the 500,000 km² limit. Draw a smaller area.</div>
        )}
      </div>
    </div>
  );
}