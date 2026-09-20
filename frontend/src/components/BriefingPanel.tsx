/** Briefing panel — shows the trilingual text in the active UI language. */

import { useTranslation } from "react-i18next";

import type { BriefingResult } from "../api/types";
import type { Lang } from "../i18n";
import { Badge, Button, Card, CardEmpty, CardHeader, CardTitle } from "./ui";

interface Props {
  briefing: BriefingResult | undefined;
  loading: boolean;
  lang: Lang;
  onGenerate: () => void;
}

export default function BriefingPanel({ briefing, loading, lang, onGenerate }: Props) {
  const { t } = useTranslation();
  return (
    <Card data-testid="briefing-panel">
      <CardHeader>
        <CardTitle>{t("panel.briefing")}</CardTitle>
        <Button variant="accent" onClick={onGenerate} disabled={loading} className="ml-auto">
          {loading ? "…" : t("briefing.generate")}
        </Button>
      </CardHeader>
      {briefing ? (
        <>
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-text-secondary">
            {briefing.briefing[lang]}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-text-muted">
            <span>
              {t("briefing.source")}: {briefing.source}
            </span>
            {briefing.verified && <Badge variant="robust">verified</Badge>}
            {briefing.model && <span className="tnum">{briefing.model}</span>}
            {briefing.issues.length > 0 && (
              <Badge variant="warning">issues: {briefing.issues.join(", ")}</Badge>
            )}
          </div>
        </>
      ) : (
        <CardEmpty>{t("briefing.empty")}</CardEmpty>
      )}
    </Card>
  );
}
