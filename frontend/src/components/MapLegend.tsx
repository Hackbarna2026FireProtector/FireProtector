/**
 * Map legend.
 *
 * The map carries four separate colour meanings — the burned contour, the
 * forecast contour ahead of the scrubber, the ignition point and the five
 * asset tiers — and none of them were labelled anywhere on screen. Collapsible
 * because the map is the one panel worth giving back space to.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { TIER_COLORS, TIER_ORDER } from "../lib/ranks";
import { Button } from "./ui";

/** Matches the contour paint expressions in MapView. */
const BURNED = "#EF4444";
const FORECAST = "#FB923C";

export default function MapLegend() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <Button
        onClick={() => setOpen(true)}
        className="absolute bottom-3 left-3 bg-panel/90 backdrop-blur"
        data-testid="legend-toggle"
      >
        {t("legend.show")}
      </Button>
    );
  }

  return (
    <div
      className="absolute bottom-3 left-3 w-52 rounded border border-border bg-panel/90 p-2 backdrop-blur"
      data-testid="map-legend"
    >
      <div className="mb-1.5 flex items-center gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          {t("legend.title")}
        </h2>
        <Button
          variant="ghost"
          onClick={() => setOpen(false)}
          aria-label={t("legend.hide")}
          className="ml-auto px-1 py-0 text-[10px]"
          data-testid="legend-toggle"
        >
          ✕
        </Button>
      </div>

      <ul className="space-y-1 text-[10px] text-text-secondary">
        <li className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-4 shrink-0 rounded-sm border"
            style={{ background: `${BURNED}55`, borderColor: BURNED }}
            aria-hidden="true"
          />
          {t("legend.burned")}
        </li>
        <li className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-4 shrink-0 rounded-sm border"
            style={{ background: `${FORECAST}22`, borderColor: FORECAST }}
            aria-hidden="true"
          />
          {t("legend.forecast")}
        </li>
        <li className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full border-2"
            style={{ background: "#EF4444", borderColor: "#FCA5A5" }}
            aria-hidden="true"
          />
          {t("legend.ignition")}
        </li>
      </ul>

      <h3 className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {t("legend.assets")}
      </h3>
      <ul className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-text-secondary">
        {TIER_ORDER.map((tier) => (
          <li key={tier} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: TIER_COLORS[tier] }}
              aria-hidden="true"
            />
            <span>{t(`tier.${tier}`)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
