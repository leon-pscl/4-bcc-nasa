export type AreaState = { kind: 'bbox'; bbox: [number, number, number, number] };

export type Cover = 'all' | 'forest' | 'farmland' | 'other';

// fixed-order key for the outside-change check; key order must not depend on object literal order
export function areaKey(area: AreaState): string {
  return `bbox:${area.bbox.join(',')}`;
}

export interface AppState {
  area: AreaState;
  start: string;
  end: string;
  view: 'count' | 'anomaly';
  focus?: string;
  tab: 'comparisons' | 'outlook' | 'methods';
  cover: Cover;
  layer: 'history' | 'outlook';
  lead: 1 | 2 | 3;
  cell?: [number, number];
}

export function parseHash(hash: string): Partial<AppState> {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const out: Partial<AppState> = {};
  const bbox = params.get('bbox');
  if (bbox) {
    const parts = bbox.split(',').map(Number);
    if (parts.length === 4 && parts.every(Number.isFinite)) {
      out.area = { kind: 'bbox', bbox: parts as [number, number, number, number] };
    }
  }
  // old URLs with point/radius fall back to the default area
  if (params.get('start')) out.start = params.get('start')!;
  if (params.get('end')) out.end = params.get('end')!;
  const view = params.get('view');
  if (view === 'count' || view === 'anomaly') out.view = view;
  const focus = params.get('focus');
  if (focus) out.focus = focus;
  const tab = params.get('tab');
  if (tab === 'comparisons' || tab === 'outlook' || tab === 'methods') out.tab = tab;
  const cover = params.get('cover');
  if (cover === 'forest' || cover === 'farmland' || cover === 'other') out.cover = cover;
  else out.cover = 'all';
  const layer = params.get('layer');
  out.layer = layer === 'outlook' ? 'outlook' : 'history';
  const lead = params.get('lead');
  out.lead = lead === '2' ? 2 : lead === '3' ? 3 : 1;
  const cell = params.get('cell');
  if (cell) {
    const parts = cell.split(',').map(Number);
    if (parts.length === 2 && parts.every(Number.isFinite)) {
      out.cell = parts as [number, number];
    }
  }
  return out;
}

export function toHash(state: AppState): string {
  const params = new URLSearchParams();
  params.set('bbox', state.area.bbox.join(','));
  params.set('start', state.start);
  params.set('end', state.end);
  params.set('view', state.view);
  if (state.focus) params.set('focus', state.focus);
  params.set('tab', state.tab);
  if (state.cover && state.cover !== 'all') params.set('cover', state.cover);
  if (state.layer === 'outlook') params.set('layer', 'outlook');
  if (state.layer === 'outlook') params.set('lead', String(state.lead));
  if (state.cell) params.set('cell', state.cell.join(','));
  return `#${params.toString()}`;
}