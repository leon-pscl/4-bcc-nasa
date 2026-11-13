export const COUNT_RAMP = ['#ffffb2', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#b10026'];

export function textOn(bg: string): string {
  // returns --ink or white based on contrast
  const hex = bg.replace('#', '');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.55 ? '#0f0f0f' : '#ffffff';
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