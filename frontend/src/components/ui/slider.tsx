/**
 * Slider — a native range input carrying the `.slider` styling from index.css.
 *
 * Native rather than Radix because this build takes no new dependencies; the
 * trade-off is that the track/thumb styling lives in CSS instead of in markup,
 * and there is no keyboard behaviour beyond what the browser gives a range
 * input (which is already arrows, Home/End and PageUp/PageDown).
 */

import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

import { cn } from "./cn";

export type SliderProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export const Slider = forwardRef<HTMLInputElement, SliderProps>(function Slider(
  { className, ...props },
  ref,
) {
  return <input ref={ref} type="range" className={cn("slider w-full", className)} {...props} />;
});

export interface SliderFieldProps extends SliderProps {
  label: ReactNode;
  /** Right-aligned readout of the current value. */
  display: ReactNode;
}

/** Label row + readout + slider — the shape every scoring parameter uses. */
export function SliderField({ label, display, id, className, ...props }: SliderFieldProps) {
  return (
    <div className={cn("block", className)}>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px]">
        <label htmlFor={id} className="text-text-secondary">
          {label}
        </label>
        <span className="tnum text-text-primary">{display}</span>
      </div>
      <Slider id={id} {...props} />
    </div>
  );
}

export default Slider;
