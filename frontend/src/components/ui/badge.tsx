/**
 * Badge — one component for every coloured status pill on screen.
 *
 * The tier, data-mode and robustness scales all used to live as separate
 * inline style maps in three components. They are the same visual object, so
 * they are one variant set here; `degraded` and `sensitive` keep distinct
 * colours on purpose, because borrowing a neighbouring scale's colour would
 * make a failure state read as a normal one.
 */

import type { HTMLAttributes } from "react";

import { cn } from "./cn";

const VARIANTS = {
  // Risk tiers.
  critical: "border-tier-critical/40 bg-tier-critical/15 text-tier-critical",
  high: "border-tier-high/40 bg-tier-high/15 text-tier-high",
  medium: "border-tier-medium/40 bg-tier-medium/15 text-tier-medium",
  low: "border-tier-low/40 bg-tier-low/15 text-tier-low",
  not_threatened: "border-tier-safe/40 bg-tier-safe/15 text-tier-safe",
  // API provenance.
  live: "border-emerald-500/40 bg-emerald-500/15 text-emerald-400",
  cached: "border-sky-500/40 bg-sky-500/15 text-sky-400",
  degraded: "border-fire-red/40 bg-fire-red/15 text-fire-red",
  // Ranking robustness.
  robust: "border-emerald-500/40 bg-emerald-500/15 text-emerald-400",
  moderate: "border-fire-amber/40 bg-fire-amber/15 text-fire-amber",
  sensitive: "border-fire-red/40 bg-fire-red/15 text-fire-red",
  // Neutral chrome.
  neutral: "border-border bg-raised text-text-secondary",
  warning: "border-fire-amber/40 bg-fire-amber/10 text-fire-amber",
} as const;

export type BadgeVariant = keyof typeof VARIANTS;

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export default function Badge({ variant = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none tracking-wide",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}
