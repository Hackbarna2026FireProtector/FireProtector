/** React-query hooks over the API client. */

import { useMutation, useQuery } from "@tanstack/react-query";

import {
  getAssets,
  getDefaults,
  getHealth,
  getScenarios,
  getSpread,
  postBriefing,
  postScore,
  postSensitivity,
} from "./client";
import type { ScoreParams } from "./types";

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: getHealth });
export const useDefaults = () => useQuery({ queryKey: ["defaults"], queryFn: getDefaults });
export const useScenarios = () => useQuery({ queryKey: ["scenarios"], queryFn: getScenarios });

export const useSpread = (scenarioId: string | undefined) =>
  useQuery({
    queryKey: ["spread", scenarioId],
    queryFn: () => getSpread(scenarioId!),
    enabled: !!scenarioId,
  });

export const useAssets = (scenarioId: string | undefined) =>
  useQuery({
    queryKey: ["assets", scenarioId],
    queryFn: () => getAssets(scenarioId!),
    enabled: !!scenarioId,
  });

export const useScore = (scenarioId: string | undefined) =>
  useMutation({ mutationFn: (params: ScoreParams) => postScore(scenarioId!, params) });

export const useSensitivity = (scenarioId: string | undefined) =>
  useMutation({ mutationFn: (params: ScoreParams) => postSensitivity(scenarioId!, params) });

export const useBriefing = (scenarioId: string | undefined) =>
  useMutation({ mutationFn: (params: ScoreParams) => postBriefing(scenarioId!, params) });
