/** Selected-asset panel: factor breakdown bars + deterministic explanation. */

import { useTranslation } from "react-i18next";

import type { Geometry, ScoredProps } from "../api/types";
import { fmtDistance, geometryDistance } from "../lib/geo";
import { TIER_COLORS, displayName, fmtEta, fmtPct, hasRealName } from "../lib/ranks";
import { Badge, Card, CardEmpty, CardHeader, CardTitle } from "./ui";

const FACTORS: { key: keyof ScoredProps; label: string; color: string }[] = [
  { key: "f_value", label: "value", color: "#38BDF8" },
  { key: "f_conf", label: "confidence", color: "#A78BFA" },
  { key: "f_vuln", label: "vulnerability", color: "#F472B6" },
  { key: "f_urgency", label: "urgency", color: "#FB923C" },
];

interface Props {
  asset: ScoredProps | undefined;
  /** Geometry of the selected asset, for the distance readout. */
  geometry?: Geometry;
  ignition?: Geometry;
  /** False when the OSM named layer never arrived — then nothing is named. */
  namesAvailable?: boolean;
}

export default function AssetDetail({
  asset,
  geometry,
  ignition,
  namesAvailable = true,
}: Props) {
  const { t } = useTranslation();

  if (!asset) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("panel.detail")}</CardTitle>
        </CardHeader>
        <CardEmpty>{t("detail.empty")}</CardEmpty>
      </Card>
    );
  }

  const distance = geometryDistance(geometry, ignition);
  const stats: { value: string; label: string }[] = [
    { value: `#${asset.rank}`, label: "rank" },
    { value: fmtEta(asset.eta_minutes), label: "ETA" },
    { value: fmtPct(asset.confidence), label: "conf." },
    { value: asset.risk.toFixed(3), label: "risk" },
  ];

  return (
    <Card data-testid="asset-detail">
      <CardHeader className="mb-1">
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: TIER_COLORS[asset.tier] }}
          aria-hidden="true"
        />
        <h2
          className={`min-w-0 flex-1 truncate ${
            hasRealName(asset, namesAvailable)
              ? "text-sm font-semibold"
              : "tnum text-xs text-text-secondary"
          }`}
          title={displayName(asset, namesAvailable)}
        >
          {displayName(asset, namesAvailable)}
        </h2>
        <Badge variant={asset.tier}>{t(`tier.${asset.tier}`)}</Badge>
      </CardHeader>

      <div className="mb-2 flex items-center gap-1.5 text-[10px] text-text-muted">
        <span>{asset.asset_type}</span>
        {distance != null && (
          <>
            <span aria-hidden="true">·</span>
            <span className="tnum">
              {fmtDistance(distance)} {t("detail.distance")}
            </span>
          </>
        )}
      </div>

      <p className="mb-2 text-[11px] leading-snug text-text-secondary">{asset.explanation}</p>

      <div className="mb-2 grid grid-cols-4 gap-1 text-center text-[10px] text-text-muted">
        {stats.map((s) => (
          <div key={s.label}>
            <div className="tnum text-xs text-text-primary">{s.value}</div>
            {s.label}
          </div>
        ))}
      </div>

      <div className="space-y-1">
        {FACTORS.map(({ key, label, color }) => (
          <div key={key} className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-[10px] text-text-muted">{label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded bg-raised">
              <div
                className="h-full rounded"
                style={{
                  width: `${Math.min(100, Math.max(0, (asset[key] as number) * 100))}%`,
                  background: color,
                }}
              />
            </div>
            <span className="tnum w-10 shrink-0 text-right text-[10px] text-text-secondary">
              {(asset[key] as number).toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-text-muted">
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
    </Card>
  );
}
