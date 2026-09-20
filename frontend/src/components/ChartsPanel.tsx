/** Recharts panels: cumulative risk curve + per-parameter sensitivity. */

import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SensitivityResult, ScoredResult } from "../api/types";

const ROBUSTNESS_COLOR = { robust: "#30D158", moderate: "#F59E0B", sensitive: "#EF4444" };

interface Props {
  result: ScoredResult | undefined;
  sensitivity: SensitivityResult | undefined;
  t: number;
}

export default function ChartsPanel({ result, sensitivity, t }: Props) {
  const { t: tr } = useTranslation();
  const cumulative = result?.summary.cumulative_risk ?? [];
  const perturbs = (sensitivity?.perturbations ?? []).filter(
    (p) => !(p.parameter === "tau" && p.multiplier === 1),
  );

  return (
    <section className="space-y-3 p-3">
      <div>
        <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("panel.charts")}
        </h2>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={cumulative} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="#23304D" strokeDasharray="3 3" />
              <XAxis
                dataKey="minute"
                tick={{ fontSize: 10, fill: "#6B7A99" }}
                tickFormatter={(m: number) => `${m}m`}
              />
              <YAxis tick={{ fontSize: 10, fill: "#6B7A99" }} />
              <Tooltip
                contentStyle={{ background: "#111A2E", border: "1px solid #23304D", fontSize: 11 }}
                labelFormatter={(m) => `${m} min`}
              />
              <ReferenceLine x={Math.round(t)} stroke="#38BDF8" strokeDasharray="4 2" />
              <Line
                type="monotone"
                dataKey="risk"
                stroke="#F97316"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <h2 className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("panel.sensitivity")}
          {sensitivity && (
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-bold normal-case"
              style={{
                color: ROBUSTNESS_COLOR[sensitivity.robustness],
                background: `${ROBUSTNESS_COLOR[sensitivity.robustness]}22`,
              }}
            >
              {sensitivity.robustness}
            </span>
          )}
        </h2>
        <div className="h-28">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={perturbs} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid stroke="#23304D" strokeDasharray="3 3" />
              <XAxis
                dataKey="parameter"
                tick={{ fontSize: 9, fill: "#6B7A99" }}
                tickFormatter={(p: string) => p.replace("w_", "w·")}
              />
              <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: "#6B7A99" }} />
              <Tooltip
                contentStyle={{ background: "#111A2E", border: "1px solid #23304D", fontSize: 11 }}
                formatter={(v, name) => [
                  typeof v === "number" ? v.toFixed(2) : String(v ?? ""),
                  String(name),
                ]}
                labelFormatter={(p) => `param: ${p}`}
              />
              <Bar dataKey="top5_overlap" fill="#38BDF8" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
