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