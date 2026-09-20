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
  const [tMin, setTMin] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const prevRanks = useRef(new Map<string, number>());

  const { data: health } = useHealth();
  const { data: defaults } = useDefaults();
  const { data: scenarios } = useScenarios();
  // One scenario at a time. The list is ordered by the seed file, and a picker
  // is the obvious next step once there is a reason to compare two.
  const scenario = scenarios?.scenarios[0];
  const { data: spread } = useSpread(scenario?.scenario_id);

  const score = useScore(scenario?.scenario_id);
  const sensitivity = useSensitivity(scenario?.scenario_id);
  const briefing = useBriefing(scenario?.scenario_id);

  useEffect(() => {
    i18n.changeLanguage(lang);
  }, [lang]);

  // Re-score when the scenario or parameters change (params already debounced
  // by the panel).
  useEffect(() => {
    if (!scenario) return;
    score.mutate(params);
    sensitivity.mutate(params);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.scenario_id, params]);

  // Track previous ranks for the ▲/▼ indicators.
  const result = score.data;
  useEffect(() => {
    if (result) prevRanks.current = rankMap(result.features);
  }, [result]);

  const horizon =
    params.horizon ??
    result?.summary.horizon_minutes ??
    (spread ? Math.max(0, ...spread.features.map((f) => f.properties.eta_minutes)) : 0);

  const selected = useMemo(
    () => result?.features.find((f) => f.properties.asset_id === selectedId)?.properties,
    [result, selectedId],
  );

  return (
    <div className="flex h-screen flex-col bg-bg">
      <Header scenario={scenario} health={health} lang={lang} onLang={setLang} />
      <div className="grid min-h-0 flex-1 grid-cols-[340px_1fr_360px]">
        <aside className="flex min-h-0 flex-col border-r border-border bg-panel">
          <RankedList
            result={result}
            prevRanks={prevRanks.current}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </aside>
        <main className="relative min-w-0">
          <MapView
            scenario={scenario}
            spread={spread}
            scored={result}
            t={tMin}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
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
          <AssetDetail asset={selected} />
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
