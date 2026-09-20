/** Shared test fixtures mirroring backend response shapes. */

import type { ScoredResult, Tier } from "./api/types";

export function scoreResult(): ScoredResult {
  const mk = (id: string, tier: Tier, rank: number, risk: number, type = "hospital") => ({
    type: "Feature" as const,
    geometry: { type: "Point", coordinates: [1.2, 41.8] },
    properties: {
      asset_id: id,
      asset_type: type,
      name: `Asset ${id}`,
      value: 80,
      vulnerability: 0.7,
      source: "osm",
      eta_minutes: 30,
      reached_at: "2026-09-19T14:30:00Z",
      confidence: 0.9,
      f_value: 0.8,
      f_conf: 0.9,
      f_vuln: 0.7,
      f_urgency: 0.7,
      risk,
      rank,
      tier,
      main_driver: "f_urgency",
      explanation: `${id} explanation`,
    },
  });
  return {
    type: "FeatureCollection",
    features: [
      mk("a1", "critical", 1, 0.5),
      mk("a2", "high", 2, 0.2),
      mk("a3", "not_threatened", 3, 0, "school"),
    ],
    summary: {
      by_tier: { critical: 1, high: 1, medium: 0, low: 0, not_threatened: 1 },
      threatened_by_type: { hospital: 2 },
      total_value_at_risk: 160,
      horizon_minutes: 300,
      cumulative_risk: [{ minute: 0, risk: 0 }],
    },
  };
}
