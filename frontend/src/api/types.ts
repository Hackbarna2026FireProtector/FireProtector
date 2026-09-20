/** API payload types — mirror the backend serializers/contracts. */

export interface Geometry {
  type: string;
  coordinates: unknown;
}

export interface Feature<G = Geometry, P = Record<string, unknown>> {
  type: "Feature";
  geometry: G;
  properties: P;
}

export interface FeatureCollection<F = Feature> {
  type: "FeatureCollection";
  features: F[];
  [key: string]: unknown;
}

/**
 * A hypothetical ignition at a coordinate — not a detected fire. There is
 * deliberately no `detected_at` and no `status`: nobody observed this, so
 * neither would be true. See CONTEXT.md.
 */
export interface Scenario {
  scenario_id: string;
  name: string;
  description: string;
  ignition_point: Geometry;
  declared_at: string;
}

export interface ContourProps {
  eta_minutes: number;
  /** Share of the Deepfire ensemble that burned this area by `eta_minutes`. */
  confidence: number;
}

export interface SpreadForecast extends FeatureCollection<Feature<Geometry, ContourProps>> {
  scenario_id: string;
  reference_time: string;
  generated_at: string;
  model: string;
}

export interface AssetProps {
  asset_id: string;
  asset_type: string;
  name: string;
  value: number;
  vulnerability: number;
  source: string;
}

export type AssetFC = FeatureCollection<Feature<Geometry, AssetProps>>;

export type Tier = "critical" | "high" | "medium" | "low" | "not_threatened";

export interface ScoredProps extends AssetProps {
  eta_minutes: number | null;
  reached_at: string | null;
  confidence: number;
  f_value: number;
  f_conf: number;
  f_vuln: number;
  f_urgency: number;
  risk: number;
  rank: number;
  tier: Tier;
  main_driver: string;
  explanation: string;
}

export interface ScoreSummary {
  by_tier: Record<Tier, number>;
  threatened_by_type: Record<string, number>;
  total_value_at_risk: number;
  horizon_minutes: number;
  cumulative_risk: { minute: number; risk: number }[];
}

export interface ScoredResult extends FeatureCollection<Feature<Geometry, ScoredProps>> {
  summary: ScoreSummary;
}

export interface Perturbation {
  parameter: string;
  multiplier: number;
  top5_overlap: number;
  top10_overlap: number;
  kendall_tau: number;
}

export interface SensitivityResult {
  robustness: "robust" | "moderate" | "sensitive";
  most_sensitive_parameter: string;
  perturbations: Perturbation[];
  rank_ranges: Record<string, number[]>;
}

export interface BriefingResult {
  briefing: { en: string; es: string; ca: string };
  source: string;
  verified: boolean;
  issues: string[];
  model: string | null;
  latency_ms: number;
}

export interface ScoreParams {
  tau: number;
  w_value: number;
  w_conf: number;
  w_vuln: number;
  w_urgency: number;
  horizon: number | null;
}

export interface ParamMeta {
  default: number | null;
  min: number;
  max: number;
  note?: string;
}

/**
 * `data_mode` is about provenance, not correctness: `live` means a fresh
 * simulation is possible, `cached` that answers come from recorded bundles,
 * and `degraded` that nothing can be forecast at all.
 */
export type DataMode = "live" | "cached" | "degraded";

export interface Health {
  status: string;
  data_mode: DataMode;
  providers: Record<string, { source: string; available: boolean; error: string | null }>;
  recorded_scenarios: string[];
}
