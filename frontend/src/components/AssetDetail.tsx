/** Selected-asset panel: factor breakdown bars + deterministic explanation. */

import { useTranslation } from "react-i18next";

import type { ScoredProps } from "../api/types";
import { TIER_COLORS, fmtEta, fmtPct } from "../lib/ranks";

const FACTORS: { key: keyof ScoredProps; label: string; color: string }[] = [
  { key: "f_value", label: "value", color: "#38BDF8" },
  { key: "f_conf", label: "confidence", color: "#A78BFA" },
  { key: "f_vuln", label: "vulnerability", color: "#F472B6" },
  { key: "f_urgency", label: "urgency", color: "#FB923C" },
];

export default function AssetDetail({ asset }: { asset: ScoredProps | undefined }) {
  const { t } = useTranslation();
  if (!asset) {
    return (
      <section className="p-3">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          {t("panel.detail")}
        </h2>
        <p className="text-xs text-text-muted">Select an asset on the map or in the list.</p>
      </section>
    );
  }
  return (
    <section className="p-3" data-testid="asset-detail">
      <div className="mb-1 flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: TIER_COLORS[asset.tier] }}
        />
        <h2 className="text-sm font-semibold">{asset.name || asset.asset_id}</h2>
        <span className="ml-auto rounded bg-raised px-1.5 py-0.5 text-[10px] uppercase text-text-secondary">
          {asset.asset_type}
        </span>
      </div>
      <p className="mb-2 text-[11px] text-text-secondary">{asset.explanation}</p>
      <div className="mb-2 grid grid-cols-4 gap-1 text-center text-[10px] text-text-muted">
        <div>
          <div className="tnum text-xs text-text-primary">#{asset.rank}</div>rank
        </div>
        <div>
          <div className="tnum text-xs text-text-primary">{fmtEta(asset.eta_minutes)}</div>ETA
        </div>
        <div>
          <div className="tnum text-xs text-text-primary">{fmtPct(asset.confidence)}</div>conf.
        </div>
        <div>
          <div className="tnum text-xs text-text-primary">{asset.risk.toFixed(3)}</div>risk
        </div>
      </div>
      <div className="space-y-1">
        {FACTORS.map(({ key, label, color }) => (
          <div key={key} className="flex items-center gap-2">
            <span className="w-24 text-[10px] text-text-muted">{label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded bg-raised">
              <div
                className="h-full rounded"
                style={{
                  width: `${Math.min(100, Math.max(0, (asset[key] as number) * 100))}%`,
                  background: color,
                }}
              />
            </div>
            <span className="tnum w-10 text-right text-[10px] text-text-secondary">
              {(asset[key] as number).toFixed(2)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3 text-[10px] text-text-muted">
        <span>
          value <span className="tnum text-text-secondary">{asset.value}</span>
        </span>
        <span>
          vuln <span className="tnum text-text-secondary">{asset.vulnerability}</span>
        </span>
        <span>
          driver{" "}
          <span className="tnum text-text-secondary">{asset.main_driver.replace("f_", "")}</span>
        </span>
      </div>
    </section>
  );
}
