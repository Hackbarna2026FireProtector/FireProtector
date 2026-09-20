/** Ranked asset list: tier filters with counts, type filter, rank-change arrows. */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Geometry, ScoredResult, Tier } from "../api/types";
import { fmtDistance, geometryDistance } from "../lib/geo";
import {
  TIER_COLORS,
  TIER_ORDER,
  displayName,
  fmtEta,
  fmtPct,
  fmtRisk,
  hasRealName,
  rankDelta,
} from "../lib/ranks";
import { Badge, Button, Checkbox, Select } from "./ui";

interface Props {
  result: ScoredResult | undefined;
  prevRanks: Map<string, number>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Ignition point, so each row can say how far away it is. */
  ignition?: Geometry;
}

export default function RankedList({ result, prevRanks, selectedId, onSelect, ignition }: Props) {
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

  // Distance to the ignition point is one of the few things that actually
  // differs between two register buildings, so it is worth precomputing.
  const distances = useMemo(() => {
    const m = new Map<string, number | null>();
    if (!ignition) return m;
    for (const f of features) {
      m.set(f.properties.asset_id, geometryDistance(f.geometry, ignition));
    }
    return m;
  }, [features, ignition]);

  const toggleTier = (tier: Tier) => {
    const next = new Set(tiers);
    if (next.has(tier)) next.delete(tier);
    else next.add(tier);
    setTiers(next);
  };

  const resetFilters = () => {
    setTiers(new Set(TIER_ORDER));
    setType("all");
    setThreatenedOnly(false);
  };

  const byTier = result?.summary.by_tier;
  const named = result?.named_layer;
  // No named layer means no row is named, whatever the register put in `name`.
  const namesAvailable = named?.available !== false;

  return (
    <section className="flex min-h-0 flex-1 flex-col p-3">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {t("panel.ranking")}
        </h2>
        {result && (
          <span className="tnum ml-auto text-[11px] text-text-muted">
            {t("filter.showing", { shown: rows.length, total: features.length })}
          </span>
        )}
      </div>

      {/* The register names every building "residential", so a list with no
          real names in it has to say why — otherwise it reads as a place with
          no critical facilities rather than a failed lookup. */}
      {named && !named.available && (
        <div
          className="mb-2 rounded border border-fire-amber/40 bg-fire-amber/10 p-2"
          data-testid="named-layer-warning"
        >
          <div className="flex items-center gap-1.5">
            <Badge variant="warning">{t("named.missing")}</Badge>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-text-secondary">
            {t("named.missing_detail")}
          </p>
        </div>
      )}

      <div className="mb-2 flex flex-wrap items-center gap-1">
        {TIER_ORDER.map((tier) => {
          const on = tiers.has(tier);
          const count = byTier?.[tier];
          return (
            <button
              key={tier}
              type="button"
              onClick={() => toggleTier(tier)}
              aria-pressed={on}
              className={`focus-ring flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-opacity ${
                on ? "opacity-100" : "opacity-30"
              }`}
              style={{ borderColor: TIER_COLORS[tier], color: TIER_COLORS[tier] }}
            >
              {t(`tier.${tier}`)}
              {count != null && <span className="tnum opacity-80">{count}</span>}
            </button>
          );
        })}
      </div>

      <div className="mb-2 flex items-center gap-2">
        <Select
          value={type}
          onChange={(e) => setType(e.target.value)}
          aria-label={t("filter.types")}
          wrapperClassName="min-w-0 flex-1"
        >
          <option value="all">
            {t("filter.types")}: {t("filter.all")}
          </option>
          {types.map((ty) => (
            <option key={ty} value={ty}>
              {ty}
            </option>
          ))}
        </Select>
        <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-[11px] text-text-secondary">
          <Checkbox
            checked={threatenedOnly}
            onChange={(e) => setThreatenedOnly(e.target.checked)}
          />
          {t("filter.threatened")}
        </label>
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto" data-testid="ranked-list">
        {rows.map((f) => {
          const p = f.properties;
          const delta = rankDelta(p.asset_id, p.rank, prevRanks);
          const selected = selectedId === p.asset_id;
          const distance = distances.get(p.asset_id);
          return (
            <button
              key={p.asset_id}
              type="button"
              onClick={() => onSelect(p.asset_id)}
              aria-current={selected}
              className={`focus-ring block w-full rounded border px-2 py-1.5 text-left transition-colors ${
                selected
                  ? "border-accent bg-accent/10"
                  : "border-transparent hover:border-border hover:bg-raised"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="tnum w-7 shrink-0 text-[11px] text-text-muted">#{p.rank}</span>
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: TIER_COLORS[p.tier] }}
                  aria-hidden="true"
                />
                {/* An id is not a name. Showing it in a mono face keeps the two
                    visually distinct once the OSM layer does arrive. */}
                <span
                  className={`min-w-0 flex-1 truncate text-xs ${
                    hasRealName(p, namesAvailable)
                      ? "font-semibold"
                      : "tnum text-text-secondary"
                  }`}
                >
                  {displayName(p, namesAvailable)}
                </span>
                <span className="tnum shrink-0 text-xs font-semibold">{fmtRisk(p.risk)}</span>
                <span
                  className={`tnum w-6 shrink-0 text-right text-[10px] ${
                    delta > 0 ? "text-fire-red" : delta < 0 ? "text-emerald-400" : "text-text-muted"
                  }`}
                  title="rank change vs previous run"
                >
                  {delta > 0 ? `▲${delta}` : delta < 0 ? `▼${-delta}` : "—"}
                </span>
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 pl-9 text-[10px] text-text-muted">
                <span className="truncate">{p.asset_type}</span>
                {distance != null && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="tnum shrink-0">{fmtDistance(distance)}</span>
                  </>
                )}
                <span aria-hidden="true">·</span>
                <span className="tnum shrink-0">{fmtEta(p.eta_minutes)}</span>
                <span aria-hidden="true">·</span>
                <span className="tnum shrink-0">{fmtPct(p.confidence)}</span>
              </div>
            </button>
          );
        })}
        {result && rows.length === 0 && (
          <div className="p-2">
            <p className="text-xs text-text-muted">{t("filter.none")}</p>
            <Button variant="outline" onClick={resetFilters} className="mt-2">
              {t("filter.clear")}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
