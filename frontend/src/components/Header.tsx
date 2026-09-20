/** Top bar: title, scenario name, data-mode badge, language switch. */

import { useTranslation } from "react-i18next";

import type { Health, Scenario } from "../api/types";
import { LANGUAGES, type Lang } from "../i18n";

// One entry per data_mode the API can report. `degraded` has its own style on
// purpose: falling through to another mode's colour would make "nothing can be
// forecast" look like a normal state.
const MODE_STYLES: Record<string, string> = {
  live: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40",
  cached: "bg-sky-500/15 text-sky-400 border-sky-500/40",
  degraded: "bg-fire-red/15 text-fire-red border-fire-red/40",
};

interface Props {
  scenario: Scenario | undefined;
  health: Health | undefined;
  lang: Lang;
  onLang: (l: Lang) => void;
}

export default function Header({ scenario, health, lang, onLang }: Props) {
  const { t } = useTranslation();
  const mode = health?.data_mode ?? "degraded";
  return (
    <header className="flex items-center gap-4 border-b border-border bg-panel px-4 py-2">
      <div>
        <h1 className="text-lg font-bold tracking-tight">{t("app.title")}</h1>
        <p className="text-[11px] text-text-muted">{t("app.subtitle")}</p>
      </div>
      {scenario && (
        <div className="ml-2 flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-fire-red" />
          {/* "Scenario:" is not decoration. Nobody detected this fire, and the
              label is what stops the header reading like an incident board. */}
          <span className="text-[11px] uppercase tracking-wide text-text-muted">
            {t("app.scenario")}
          </span>
          <span className="font-semibold">{scenario.name}</span>
          <span className="text-xs text-text-muted">{scenario.scenario_id}</span>
        </div>
      )}
      <div className="ml-auto flex items-center gap-3">
        <span
          className={`rounded border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${MODE_STYLES[mode] ?? MODE_STYLES.degraded}`}
          data-testid="data-mode-badge"
        >
          {mode}
        </span>
        <div className="flex overflow-hidden rounded border border-border">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => onLang(l.code)}
              className={`px-2 py-1 text-[11px] font-semibold ${
                lang === l.code ? "bg-accent/20 text-accent" : "text-text-secondary hover:bg-raised"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
