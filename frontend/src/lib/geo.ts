const R = 6371; // km

export type Edges = { n: number; s: number; e: number; w: number };

export function parseEdges(n: string, s: string, e: string, w: string): Edges | null {
  const N = Number(n), S = Number(s), E = Number(e), W = Number(w);
  if ([N, S, E, W].some((v) => !Number.isFinite(v))) return null;
  if (N < -90 || N > 90 || S < -90 || S > 90) return null;
  if (E < -180 || E > 180 || W < -180 || W > 180) return null;
  if (S >= N) return null; // south must be below north
  if (W >= E) return null; // west must be left of east (no antimeridian crossing)
  return { n: N, s: S, e: E, w: W };
}

export function areaKm2(n: number, s: number, e: number, w: number): number {
  // R^2 * (sin N - sin S) * (E - W in radians)
  const toRad = (d: number) => (d * Math.PI) / 180;
  return R * R * (Math.sin(toRad(n)) - Math.sin(toRad(s))) * toRad(e - w);
}

export function wrapLon(lon: number): number {
  let v = lon;
  while (v > 180) v -= 360;
  while (v <= -180) v += 360;
  return v;
}

export function round4(x: number): number {
  return Math.round(x * 10000) / 10000;
}

export function cornersToEdges(aLat: number, aLon: number, bLat: number, bLon: number) {
  const n = round4(Math.max(aLat, bLat));
  const s = round4(Math.min(aLat, bLat));
  const e = round4(wrapLon(Math.max(aLon, bLon)));
  const w = round4(wrapLon(Math.min(aLon, bLon)));
  return { n: String(n), s: String(s), e: String(e), w: String(w) };
}

export const MAX_AREA_KM2 = 500000;

export function validateEdges(n: string, s: string, e: string, w: string): string | null {
  const N = Number(n), S = Number(s), E = Number(e), W = Number(w);
  if ([n, s, e, w].some((v) => v.trim() === '') || [N, S, E, W].some((v) => !Number.isFinite(v))) return 'Enter all four edges in decimal degrees.';
  if (N < -90 || N > 90 || S < -90 || S > 90) return 'North and South must be between −90 and 90.';
  if (E < -180 || E > 180 || W < -180 || W > 180) return 'East and West must be between −180 and 180.';
  if (S >= N) return 'The South edge must be below the North edge.';
  if (W >= E) return "The West edge must be left of the East edge (areas can't cross the 180° line).";
  if (areaKm2(N, S, E, W) > MAX_AREA_KM2) return 'Larger than the 500,000 km² limit. Draw a smaller area.';
  return null;
}

export function insideRegion(edges: Edges, regionBbox: [number, number, number, number]): boolean {
  const [rw, rs, re, rn] = regionBbox;
  return edges.w >= rw && edges.e <= re && edges.s >= rs && edges.n <= rn;
}

export function pointAreaKm2(radiusKm: number): number {
  return Math.PI * radiusKm * radiusKm;
}

export function validatePoint(lat: string, lon: string, radius: string): string | null {
  const la = Number(lat), lo = Number(lon), r = Number(radius);
  if ([lat, lon, radius].some((v) => v.trim() === '') || [la, lo, r].some((v) => !Number.isFinite(v))) {
    return 'Enter a latitude, a longitude and a radius.';
  }
  if (la < -90 || la > 90) return 'North and South must be between −90 and 90.';
  if (lo < -180 || lo > 180) return 'East and West must be between −180 and 180.';
  if (r < 1 || r > 500) return 'The radius must be between 1 and 500 km.';
  if (pointAreaKm2(r) > MAX_AREA_KM2) return 'Larger than the 500,000 km² limit. Draw a smaller area.';
  return null;
}

export function pointInRegion(lat: number, lon: number, regionBbox: [number, number, number, number]): boolean {
  const [rw, rs, re, rn] = regionBbox;
  return lon >= rw && lon <= re && lat >= rs && lat <= rn;
}