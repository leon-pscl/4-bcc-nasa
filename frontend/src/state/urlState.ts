export type AreaState =
  | { kind: 'bbox'; bbox: [number, number, number, number] }
  | { kind: 'point'; point: [number, number]; radius_km: number };

export interface AppState {
  area: AreaState;
  start: string;
  end: string;
  view: 'count' | 'anomaly';
  focus?: string;
  tab: 'comparisons' | 'watchlist' | 'methods';
}

export function parseHash(hash: string): Partial<AppState> {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const out: Partial<AppState> = {};
  const bbox = params.get('bbox');
  const point = params.get('point');
  const radius = params.get('radius_km');
  if (bbox) {
    const parts = bbox.split(',').map(Number);
    if (parts.length === 4 && parts.every(Number.isFinite)) {
      out.area = { kind: 'bbox', bbox: parts as [number, number, number, number] };
    }
  } else if (point && radius) {
    const p = point.split(',').map(Number);
    if (p.length === 2 && p.every(Number.isFinite) && Number.isFinite(Number(radius))) {
      out.area = { kind: 'point', point: p as [number, number], radius_km: Number(radius) };
    }
  }
  if (params.get('start')) out.start = params.get('start')!;
  if (params.get('end')) out.end = params.get('end')!;
  const view = params.get('view');
  if (view === 'count' || view === 'anomaly') out.view = view;
  const focus = params.get('focus');
  if (focus) out.focus = focus;
  const tab = params.get('tab');
  if (tab === 'comparisons' || tab === 'watchlist' || tab === 'methods') out.tab = tab;
  return out;
}

export function toHash(state: AppState): string {
  const params = new URLSearchParams();
  if (state.area.kind === 'bbox') params.set('bbox', state.area.bbox.join(','));
  else {
    params.set('point', state.area.point.join(','));
    params.set('radius_km', String(state.area.radius_km));
  }
  params.set('start', state.start);
  params.set('end', state.end);
  params.set('view', state.view);
  if (state.focus) params.set('focus', state.focus);
  params.set('tab', state.tab);
  return `#${params.toString()}`;
}