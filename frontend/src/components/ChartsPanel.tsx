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
import { Badge, Card, CardTitle } from "./ui";

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
    <Card className="space-y-3">
      <div>
        <CardTitle className="mb-1 block">{tr("panel.charts")}</CardTitle>
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
        <CardTitle className="mb-1 flex items-center gap-2">
          {tr("panel.sensitivity")}
          {sensitivity && (
            <Badge variant={sensitivity.robustness}>{sensitivity.robustness}</Badge>
          )}
        </CardTitle>
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
    </Card>
  );
}
