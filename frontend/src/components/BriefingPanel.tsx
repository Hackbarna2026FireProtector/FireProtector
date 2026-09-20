/** Briefing panel — shows the trilingual text in the active UI language. */

import { useTranslation } from "react-i18next";

import type { BriefingResult } from "../api/types";
import type { Lang } from "../i18n";

interface Props {
  briefing: BriefingResult | undefined;
  loading: boolean;
  lang: Lang;
  onGenerate: () => void;
}

export default function BriefingPanel({ briefing, loading, lang, onGenerate }: Props) {
  const { t } = useTranslation();
  return (
    <section className="p-3" data-testid="briefing-panel">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {t("panel.briefing")}
        </h2>
        <button
          onClick={onGenerate}
          disabled={loading}
          className="ml-auto rounded border border-accent/50 bg-accent/10 px-2 py-0.5 text-[11px] font-semibold text-accent hover:bg-accent/20 disabled:opacity-40"
        >
          {loading ? "…" : t("briefing.generate")}
        </button>
      </div>
      {briefing ? (
        <>
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-text-secondary">
            {briefing.briefing[lang]}
          </p>
          <p className="mt-2 text-[10px] text-text-muted">
            {t("briefing.source")}: {briefing.source}
            {briefing.verified ? " · verified" : ""}
            {briefing.model ? ` · ${briefing.model}` : ""}
            {briefing.issues.length > 0 && (
              <span className="text-fire-amber"> · issues: {briefing.issues.join(", ")}</span>
            )}
          </p>
        </>
      ) : (
        <p className="text-xs text-text-muted">—</p>
      )}
    </section>
  );
}
