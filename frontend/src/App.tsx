/** Command-centre layout: ranking | map | controls/detail/charts/briefing. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useBriefing,
  useDefaults,
  useHealth,
  useScenarios,
  useScore,
  useSensitivity,
  useSpread,
} from "./api/hooks";
import type { ScoreParams } from "./api/types";
import AssetDetail from "./components/AssetDetail";
import BriefingPanel from "./components/BriefingPanel";
import ChartsPanel from "./components/ChartsPanel";
import ControlPanel from "./components/ControlPanel";
import Header from "./components/Header";
import MapLegend from "./components/MapLegend";
import RankedList from "./components/RankedList";
import i18n, { type Lang } from "./i18n";
import { rankMap } from "./lib/ranks";
import MapView from "./map/MapView";

const DEFAULT_PARAMS: ScoreParams = {
  tau: 90,
  w_value: 1,
  w_conf: 1,
  w_vuln: 1,
  w_urgency: 1,
  horizon: null,
};

export default function App() {
  const { t } = useTranslation();
  const [lang, setLang] = useState<Lang>("en");
  const [params, setParams] = useState<ScoreParams>(DEFAULT_PARAMS);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [tMin, setTMin] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const prevRanks = useRef(new Map<string, number>());

  const { data: health } = useHealth();
  const { data: defaults } = useDefaults();
  const { data: scenarios } = useScenarios();

  const scenarioList = useMemo(() => scenarios?.scenarios ?? [], [scenarios]);
  // The picker owns the choice once the list arrives; until then, and whenever
  // the current id is not in the list, fall back to the seed file's order.
  const activeId =
    scenarioId && scenarioList.some((s) => s.scenario_id === scenarioId)
      ? scenarioId
      : scenarioList[0]?.scenario_id;
  const scenario = scenarioList.find((s) => s.scenario_id === activeId);

  const { data: spread } = useSpread(activeId);

  const score = useScore(activeId);
  const sensitivity = useSensitivity(activeId);
  const briefing = useBriefing(activeId);

  useEffect(() => {
    i18n.changeLanguage(lang);
  }, [lang]);

  // Switching scenario invalidates everything on screen. This effect is
  // declared before the scoring one so the clear always lands before the
  // refetch that replaces it — otherwise the new request is reset mid-flight
  // and the panels stay empty.
  useEffect(() => {
    setSelectedId(null);
    setTMin(0);
    setPlaying(false);
    prevRanks.current = new Map();
    score.reset();
    sensitivity.reset();
    briefing.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // Re-score when the scenario or parameters change (params already debounced
  // by the panel).
  useEffect(() => {
    if (!activeId) return;
    score.mutate(params);
    sensitivity.mutate(params);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, params]);

  // Track previous ranks for the ▲/▼ indicators.
  const result = score.data;
  useEffect(() => {
    if (result) prevRanks.current = rankMap(result.features);
  }, [result]);

  const horizon =
    params.horizon ??
    result?.summary.horizon_minutes ??
    (spread ? Math.max(0, ...spread.features.map((f) => f.properties.eta_minutes)) : 0);

  const selectedFeature = useMemo(
    () => result?.features.find((f) => f.properties.asset_id === selectedId),
    [result, selectedId],
  );

  return (
    <div className="flex h-screen flex-col bg-bg">
      <Header
        scenarios={scenarioList}
        scenarioId={activeId}
        onScenario={setScenarioId}
        health={health}
        lang={lang}
        onLang={setLang}
      />
      <div className="grid min-h-0 flex-1 grid-cols-[340px_1fr_360px]">
        <aside className="flex min-h-0 flex-col border-r border-border bg-panel">
          <RankedList
            result={result}
            prevRanks={prevRanks.current}
            selectedId={selectedId}
            onSelect={setSelectedId}
            ignition={scenario?.ignition_point}
          />
        </aside>
        <main className="relative min-w-0">
          <MapView
            scenario={scenario}
            scenarios={scenarioList}
            onScenario={setScenarioId}
            spread={spread}
            scored={result}
            t={tMin}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <MapLegend />
          {score.isPending && (
            <div className="absolute left-3 top-3 rounded bg-panel/90 px-2 py-1 text-xs text-text-secondary">
              {t("state.loading")}
            </div>
          )}
          {score.isError && (
            <div className="absolute left-3 top-3 rounded bg-fire-red/20 px-2 py-1 text-xs text-fire-red">
              {t("state.error")}: {score.error.message}
            </div>
          )}
        </main>
        <aside className="flex min-h-0 flex-col divide-y divide-border overflow-y-auto border-l border-border bg-panel">
          <ControlPanel
            params={params}
            meta={defaults?.parameters}
            onParams={setParams}
            t={tMin}
            horizon={horizon}
            playing={playing}
            onT={setTMin}
            onPlay={setPlaying}
          />
          <AssetDetail
            asset={selectedFeature?.properties}
            geometry={selectedFeature?.geometry}
            ignition={scenario?.ignition_point}
            namesAvailable={result?.named_layer?.available !== false}
          />
          <ChartsPanel result={result} sensitivity={sensitivity.data} t={tMin} />
          <BriefingPanel
            briefing={briefing.data}
            loading={briefing.isPending}
            lang={lang}
            onGenerate={() => briefing.mutate(params)}
          />
        </aside>
      </div>
    </div>
  );
}
