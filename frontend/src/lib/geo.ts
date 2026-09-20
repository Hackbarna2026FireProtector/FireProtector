/**
 * Distance helpers for telling otherwise-identical assets apart.
 *
 * Every residential row in the register shares a name, a type, a value and a
 * vulnerability, so the only things that distinguish two of them on screen are
 * their id, their arrival time and how far they sit from the ignition point.
 */

import type { Geometry } from "../api/types";

const EARTH_RADIUS_M = 6_371_000;

/** First [lng, lat] pair found in a GeoJSON coordinate array, or null. */
export function firstPoint(coords: unknown): [number, number] | null {
  if (!Array.isArray(coords)) return null;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    return [coords[0], coords[1]];
  }
  for (const c of coords) {
    const found = firstPoint(c);
    if (found) return found;
  }
  return null;
}

/** Great-circle distance in metres between two [lng, lat] pairs. */
export function haversineMeters(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const [lng1, lat1] = a;
  const [lng2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Metres between two geometries, taking each one's first coordinate. */
export function geometryDistance(a: Geometry | undefined, b: Geometry | undefined): number | null {
  if (!a || !b) return null;
  const pa = firstPoint(a.coordinates);
  const pb = firstPoint(b.coordinates);
  if (!pa || !pb) return null;
  return haversineMeters(pa, pb);
}

/** "840 m" under a kilometre, "1.4 km" above it. */
export function fmtDistance(meters: number | null): string {
  if (meters == null || !Number.isFinite(meters)) return "—";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}
