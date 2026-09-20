/** Pure helpers: rank deltas, tier styling, formatting. */

import type { ScoredProps, Tier } from "../api/types";

export const TIER_ORDER: Tier[] = ["critical", "high", "medium", "low", "not_threatened"];

export const TIER_COLORS: Record<Tier, string> = {
  critical: "#EF4444",
  high: "#F97316",
  medium: "#F59E0B",
  low: "#EAB308",
  not_threatened: "#64748B",
};

/** Rank delta vs a previous run: positive = moved up (worse). */
export function rankDelta(assetId: string, newRank: number, prev: Map<string, number>): number {
  const old = prev.get(assetId);
  return old === undefined ? 0 : old - newRank;
}

export function rankMap(features: { properties: ScoredProps }[]): Map<string, number> {
  return new Map(features.map((f) => [f.properties.asset_id, f.properties.rank]));
}

export const fmtEta = (eta: number | null): string =>
  eta == null ? "—" : `~${Math.round(eta)} min`;

export const fmtPct = (x: number): string => `${Math.round(x * 100)}%`;

export const fmtRisk = (x: number): string => (x > 0 ? x.toFixed(3) : "0");

/**
 * Whether a row carries a real name.
 *
 * Two things have to hold. The register labels every row "residential" whatever
 * it actually is — a storage tank included — so the only rows that can carry a
 * real name are the ones the OpenStreetMap layer matched; `namesAvailable` is
 * that layer's own report, and when it is false nothing on screen is named.
 * Within an available layer, a name that merely repeats the type is still the
 * register's placeholder showing through.
 */
export function hasRealName(
  p: Pick<ScoredProps, "name" | "asset_type">,
  namesAvailable = true,
): boolean {
  if (!namesAvailable) return false;
  return !!p.name && p.name.toLowerCase() !== p.asset_type.toLowerCase();
}

/** The name when there is one, the id when there is not. */
export function displayName(
  p: Pick<ScoredProps, "name" | "asset_type" | "asset_id">,
  namesAvailable = true,
): string {
  return hasRealName(p, namesAvailable) ? p.name : p.asset_id;
}
