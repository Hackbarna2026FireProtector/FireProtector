/** Scenario controls: debounced scoring-parameter sliders + forecast time scrubber. */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ParamMeta, ScoreParams } from "../api/types";
import { Button, Card, CardTitle, Checkbox, Slider, SliderField } from "./ui";

const SLIDERS: { key: keyof ScoreParams; label: string; step: number }[] = [
  { key: "tau", label: "controls.tau", step: 5 },
  { key: "w_value", label: "controls.w_value", step: 0.1 },
  { key: "w_conf", label: "controls.w_conf", step: 0.1 },
  { key: "w_vuln", label: "controls.w_vuln", step: 0.1 },
  { key: "w_urgency", label: "controls.w_urgency", step: 0.1 },
];

interface Props {
  params: ScoreParams;
  meta: Record<string, ParamMeta> | undefined;
  onParams: (p: ScoreParams) => void;
  t: number;
  horizon: number;
  playing: boolean;
  onT: (t: number) => void;
  onPlay: (playing: boolean) => void;
}

export default function ControlPanel({
  params,
  meta,
  onParams,
  t,
  horizon,
  playing,
  onT,
  onPlay,
}: Props) {
  const { t: tr } = useTranslation();
  const [draft, setDraft] = useState(params);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const horizonAuto = params.horizon == null;
  const atEnd = t >= horizon;

  useEffect(() => setDraft(params), [params]);

  // Debounce slider drags so /score isn't spammed.
  const update = (key: keyof ScoreParams, value: number | null) => {
    const next = { ...draft, [key]: value };
    setDraft(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onParams(next), 300);
  };

  // Playback clock.
  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => onT(Math.min(t + 5, horizon)), 150);
    return () => clearInterval(iv);
  }, [playing, t, horizon, onT]);

  useEffect(() => {
    if (playing && t >= horizon) onPlay(false);
  }, [t, horizon, playing, onPlay]);

  return (
    <Card className="space-y-4">
      <div>
        <CardTitle className="mb-2 block">{tr("panel.timeline")}</CardTitle>
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            onClick={() => (atEnd ? onT(0) : onPlay(!playing))}
            aria-label="play/pause"
            data-testid="play-button"
          >
            {atEnd ? "↺" : playing ? "❚❚" : "▶"}
          </Button>
          <Slider
            min={0}
            max={Math.ceil(horizon)}
            step={1}
            value={t}
            onChange={(e) => onT(Number(e.target.value))}
            aria-label={tr("panel.timeline")}
            className="flex-1"
            data-testid="time-slider"
          />
          <span className="tnum w-16 shrink-0 text-right text-xs text-text-secondary">
            {Math.round(t)} / {Math.round(horizon)} min
          </span>
        </div>
      </div>

      <div>
        <CardTitle className="mb-2 block">{tr("panel.controls")}</CardTitle>
        <div className="space-y-2.5">
          {SLIDERS.map(({ key, label, step }) => {
            const m = meta?.[key];
            return (
              <SliderField
                key={key}
                id={`param-${key}`}
                label={tr(label)}
                display={(draft[key] as number).toFixed(step < 1 ? 1 : 0)}
                min={m?.min ?? 0}
                max={m?.max ?? 100}
                step={step}
                value={draft[key] as number}
                onChange={(e) => update(key, Number(e.target.value))}
              />
            );
          })}
          <div>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px]">
              <label htmlFor="param-horizon" className="text-text-secondary">
                {tr("controls.horizon")}
              </label>
              <span className="tnum text-text-primary">
                {horizonAuto ? tr("controls.auto") : `${draft.horizon} min`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={horizonAuto}
                aria-label={tr("controls.auto")}
                onChange={(e) => update("horizon", e.target.checked ? null : Math.ceil(horizon))}
              />
              <Slider
                id="param-horizon"
                min={meta?.horizon?.min ?? 0}
                max={meta?.horizon?.max ?? 1440}
                step={10}
                disabled={horizonAuto}
                value={draft.horizon ?? Math.ceil(horizon)}
                onChange={(e) => update("horizon", Number(e.target.value))}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
