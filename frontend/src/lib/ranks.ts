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
