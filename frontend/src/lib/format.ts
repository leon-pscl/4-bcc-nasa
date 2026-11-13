export function formatNumber(n: number): string {
  if (n === 0) return '0';
  if (Math.abs(n) < 1) return '<1';
  return Math.round(n).toLocaleString('en-US');
}

export function formatSignedPct(n: number): string {
  if (n > 0) return `+${n.toFixed(0)}%`;
  if (n < 0) return `\u2212${Math.abs(n).toFixed(0)}%`;
  return '0%';
}

export function formatDate(d: string | Date): string {
  const date = typeof d === 'string' ? new Date(d) : d;
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatLat(lat: number): string {
  const dir = lat >= 0 ? 'N' : 'S';
  return `${Math.abs(lat).toFixed(1)}°${dir}`;
}

export function formatLon(lon: number): string {
  const dir = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lon).toFixed(1)}°${dir}`;
}