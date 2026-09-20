/** Scenario controls: debounced scoring-parameter sliders + forecast time scrubber. */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ParamMeta, ScoreParams } from "../api/types";

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
    <section className="space-y-4 p-3">
      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("panel.timeline")}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => (t >= horizon ? onT(0) : onPlay(!playing))}
            className="w-8 rounded border border-border bg-raised py-1 text-sm hover:border-accent"
            aria-label="play/pause"
            data-testid="play-button"
          >
            {t >= horizon ? "↺" : playing ? "❚❚" : "▶"}
          </button>
          <input
            type="range"
            min={0}
            max={Math.ceil(horizon)}
            step={1}
            value={t}
            onChange={(e) => onT(Number(e.target.value))}
            className="flex-1 accent-accent"
            data-testid="time-slider"
          />
          <span className="tnum w-16 text-right text-xs text-text-secondary">
            {Math.round(t)} / {Math.round(horizon)} min
          </span>
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
          {tr("panel.controls")}
        </h2>
        <div className="space-y-2">
          {SLIDERS.map(({ key, label, step }) => {
            const m = meta?.[key];
            return (
              <label key={key} className="block">
                <div className="flex justify-between text-[11px] text-text-secondary">
                  <span>{tr(label)}</span>
                  <span className="tnum">{(draft[key] as number).toFixed(step < 1 ? 1 : 0)}</span>
                </div>
                <input
                  type="range"
                  min={m?.min ?? 0}
                  max={m?.max ?? 100}
                  step={step}
                  value={draft[key] as number}
                  onChange={(e) => update(key, Number(e.target.value))}
                  className="w-full accent-accent"
                />
              </label>
            );
          })}
          <label className="block">
            <div className="flex justify-between text-[11px] text-text-secondary">
              <span>{tr("controls.horizon")}</span>
              <span className="tnum">
                {horizonAuto ? tr("controls.auto") : `${draft.horizon} min`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={horizonAuto}
                onChange={(e) => update("horizon", e.target.checked ? null : Math.ceil(horizon))}
              />
              <input
                type="range"
                min={meta?.horizon?.min ?? 0}
                max={meta?.horizon?.max ?? 1440}
                step={10}
                disabled={horizonAuto}
                value={draft.horizon ?? Math.ceil(horizon)}
                onChange={(e) => update("horizon", Number(e.target.value))}
                className="flex-1 accent-accent disabled:opacity-40"
              />
            </div>
          </label>
        </div>
      </div>
    </section>
  );
}
