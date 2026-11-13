export const COUNT_RAMP = ['#ffffb2', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#b10026'];

function relLum(hex: string): number {
  const v = hex.replace('#', '');
  const ch = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

export function textOn(bg: string): string {
  const l = relLum(bg);
  const ink = relLum('#0f0f0f');
  const white = 1;
  const cInk = (Math.max(l, ink) + 0.05) / (Math.min(l, ink) + 0.05);
  const cWhite = (Math.max(l, white) + 0.05) / (Math.min(l, white) + 0.05);
  return cWhite >= cInk ? '#ffffff' : '#0f0f0f';
}

export function quantileBins(values: number[], bins = 7): number[] {
  const nz = values.filter((v) => v > 0).slice().sort((a, b) => a - b);
  const out: number[] = [];
  for (let i = 1; i <= bins; i++) {
    const idx = Math.min(nz.length - 1, Math.floor((i / (bins + 1)) * nz.length));
    out.push(nz.length ? nz[idx] : 0);
  }
  return out;
}

export function countColor(value: number, bins: number[]): string {
  if (value <= 0) return '#f0f0f0';
  let i = bins.findIndex((b) => value <= b);
  if (i < 0) i = bins.length - 1;
  return COUNT_RAMP[i] ?? COUNT_RAMP[COUNT_RAMP.length - 1];
}

export const ANOMALY_BINS = [
  { max: -75, color: '#2166ac', label: 'below −75%' },
  { max: -40, color: '#67a9cf', label: '−75 to −40%' },
  { max: -10, color: '#d1e5f0', label: '−40 to −10%' },
  { max: 10, color: '#f7f7f7', label: 'within ±10%' },
  { max: 40, color: '#fddbc7', label: '+10 to +40%' },
  { max: 75, color: '#ef8a62', label: '+40 to +75%' },
  { max: Infinity, color: '#b2182b', label: 'above +75%' },
];

export function anomalyColor(pct: number | null): string {
  if (pct === null) return '#f0f0f0';
  for (const b of ANOMALY_BINS) if (pct <= b.max) return b.color;
  return '#b2182b';
}