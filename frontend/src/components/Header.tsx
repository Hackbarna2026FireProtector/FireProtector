/** Top bar: title, scenario picker, data-mode badge, language switch. */

import { useTranslation } from "react-i18next";

import type { DataMode, Health, Scenario } from "../api/types";
import { LANGUAGES, type Lang } from "../i18n";
import { Badge, Button, Select } from "./ui";

const MODES: DataMode[] = ["live", "cached", "degraded"];

interface Props {
  scenarios: Scenario[];
  scenarioId: string | undefined;
  onScenario: (id: string) => void;
  health: Health | undefined;
  lang: Lang;
  onLang: (l: Lang) => void;
}

export default function Header({
  scenarios,
  scenarioId,
  onScenario,
  health,
  lang,
  onLang,
}: Props) {
  const { t } = useTranslation();
  // `degraded` is the honest default: until /health answers, nothing is known
  // to be forecastable, and an unknown state must not look like a healthy one.
  const reported = health?.data_mode;
  const mode: DataMode = reported && MODES.includes(reported) ? reported : "degraded";
  const scenario = scenarios.find((s) => s.scenario_id === scenarioId);

  return (
    <header className="flex items-center gap-4 border-b border-border bg-panel px-4 py-2">
      <div>
        <h1 className="text-lg font-bold tracking-tight">{t("app.title")}</h1>
        <p className="text-[11px] text-text-muted">{t("app.subtitle")}</p>
      </div>
      {scenarios.length > 0 && (
        <div className="ml-2 flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-fire-red" />
          {/* "Scenario:" is not decoration. Nobody detected this fire, and the
              label is what stops the header reading like an incident board. */}
          <span className="shrink-0 text-[11px] uppercase tracking-wide text-text-muted">
            {t("app.scenario")}
          </span>
          <Select
            value={scenarioId ?? ""}
            onChange={(e) => onScenario(e.target.value)}
            aria-label={t("app.pick_scenario")}
            data-testid="scenario-select"
            className="py-1 text-xs font-semibold"
            wrapperClassName="min-w-0"
          >
            {scenarios.map((s) => (
              <option key={s.scenario_id} value={s.scenario_id}>
                {s.name}
              </option>
            ))}
          </Select>
          {scenario && (
            <span className="tnum shrink-0 text-[11px] text-text-muted">
              {scenario.scenario_id}
            </span>
          )}
        </div>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-3">
        <Badge variant={mode} data-testid="data-mode-badge">
          {mode}
        </Badge>
        <div className="flex overflow-hidden rounded border border-border">
          {LANGUAGES.map((l) => (
            <Button
              key={l.code}
              variant="ghost"
              onClick={() => onLang(l.code)}
              aria-pressed={lang === l.code}
              className={`rounded-none border-0 px-2 py-1 ${
                lang === l.code ? "bg-accent/20 text-accent hover:bg-accent/20" : ""
              }`}
            >
              {l.label}
            </Button>
          ))}
        </div>
      </div>
    </header>
  );
}
