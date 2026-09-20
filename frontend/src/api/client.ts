/** Thin fetch wrapper — every error arrives as ApiError with the envelope fields. */

import type {
  AssetFC,
  BriefingResult,
  Health,
  ParamMeta,
  Scenario,
  ScoreParams,
  ScoredResult,
  SensitivityResult,
  SpreadForecast,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    // The contract's errors are {error: {code, message}}; FastAPI's own are
    // {detail: "..."}, and both reach this client.
    const detail = (body as { detail?: string } | null)?.detail;
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? detail ?? res.statusText,
    );
  }
  return body as T;
}

const post = <T>(path: string, body: unknown): Promise<T> =>
  api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getHealth = () => api<Health>("/api/health");
export const getDefaults = () =>
  api<{ parameters: Record<string, ParamMeta> }>("/api/config/defaults");

/** Hypothetical ignitions, not detected fires — see CONTEXT.md. */
export const getScenarios = () => api<{ scenarios: Scenario[] }>("/api/scenarios");

export const getSpread = (scenarioId: string) =>
  api<SpreadForecast>(`/api/scenarios/${scenarioId}/spread`);

/** The reached set, unscored. */
export const getAssets = (scenarioId: string) =>
  api<AssetFC>(`/api/scenarios/${scenarioId}/assets`);

export const postScore = (scenarioId: string, params: ScoreParams) =>
  post<ScoredResult>(`/api/scenarios/${scenarioId}/score`, params);

export const postSensitivity = (scenarioId: string, params: ScoreParams) =>
  post<SensitivityResult>(`/api/scenarios/${scenarioId}/sensitivity`, params);

export const postBriefing = (scenarioId: string, params: ScoreParams, topN = 5) =>
  post<BriefingResult>(`/api/scenarios/${scenarioId}/briefing`, {
    parameters: params,
    top_n: topN,
  });
