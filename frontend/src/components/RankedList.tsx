/** Ranked asset list: tier filters, type filter, threatened-only, rank-change arrows. */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ScoredResult, Tier } from "../api/types";
import { TIER_COLORS, TIER_ORDER, fmtEta, fmtPct, fmtRisk, rankDelta } from "../lib/ranks";

interface Props {
  result: ScoredResult | undefined;
  prevRanks: Map<string, number>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function RankedList({ result, prevRanks, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  const [tiers, setTiers] = useState<Set<Tier>>(new Set(TIER_ORDER));
  const [type, setType] = useState<string>("all");
  const [threatenedOnly, setThreatenedOnly] = useState(false);

  const features = useMemo(() => result?.features ?? [], [result]);
  const types = useMemo(
    () => [...new Set(features.map((f) => f.properties.asset_type))].sort(),
    [features],
  );
  const rows = useMemo(
    () =>
      features.filter(
        (f) =>
          tiers.has(f.properties.tier) &&
          (type === "all" || f.properties.asset_type === type) &&
          (!threatenedOnly || f.properties.risk > 0),
      ),
    [features, tiers, type, threatenedOnly],
  );

  const toggleTier = (tier: Tier) => {
    const next = new Set(tiers);
    if (next.has(tier)) next.delete(tier);
    else next.add(tier);
    setTiers(next);
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col p-3">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
        {t("panel.ranking")}
      </h2>
      <div className="mb-2 flex flex-wrap items-center gap-1">
        {TIER_ORDER.map((tier) => (
          <button
            key={tier}
            onClick={() => toggleTier(tier)}
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
              tiers.has(tier) ? "opacity-100" : "opacity-30"
            }`}
            style={{ borderColor: TIER_COLORS[tier], color: TIER_COLORS[tier] }}
          >
            {t(`tier.${tier}`)}
          </button>
        ))}
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="ml-auto rounded border border-border bg-raised px-1 py-0.5 text-[11px]"
          aria-label={t("filter.types")}
        >
          <option value="all">{t("filter.types")}: all</option>
          {types.map((ty) => (
            <option key={ty} value={ty}>
              {ty}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-[11px] text-text-secondary">
          <input
            type="checkbox"
            checked={threatenedOnly}
            onChange={(e) => setThreatenedOnly(e.target.checked)}
          />
          {t("filter.threatened")}
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="ranked-list">
        {rows.map((f) => {
          const p = f.properties;
          const delta = rankDelta(p.asset_id, p.rank, prevRanks);
          return (
            <button
              key={p.asset_id}
              onClick={() => onSelect(p.asset_id)}
              className={`mb-1 flex w-full items-center gap-2 rounded border px-2 py-1.5 text-left text-xs ${
                selectedId === p.asset_id
                  ? "border-accent bg-accent/10"
                  : "border-transparent hover:bg-raised"
              }`}
            >
              <span className="tnum w-6 text-text-muted">#{p.rank}</span>
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: TIER_COLORS[p.tier] }}
                title={t(`tier.${p.tier}`)}
              />
              <span className="min-w-0 flex-1 truncate font-medium">{p.name || p.asset_id}</span>
              <span className="text-text-muted">{p.asset_type}</span>
              <span className="tnum text-text-secondary">{fmtEta(p.eta_minutes)}</span>
              <span className="tnum text-text-secondary">{fmtPct(p.confidence)}</span>
              <span className="tnum w-12 text-right font-semibold">{fmtRisk(p.risk)}</span>
              <span
                className={`tnum w-6 text-right ${
                  delta > 0 ? "text-fire-red" : delta < 0 ? "text-emerald-400" : "text-text-muted"
                }`}
                title="rank change vs previous run"
              >
                {delta > 0 ? `▲${delta}` : delta < 0 ? `▼${-delta}` : "—"}
              </span>
            </button>
          );
        })}
        {result && rows.length === 0 && (
          <p className="p-2 text-xs text-text-muted">No assets match the filters.</p>
        )}
      </div>
    </section>
  );
}
