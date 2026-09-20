/** Select — a native select with the chevron drawn alongside it. */

import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "./cn";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  /** Width of the wrapper; the select itself always fills it. */
  wrapperClassName?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, wrapperClassName, children, ...props },
  ref,
) {
  return (
    <div className={cn("relative inline-flex items-center", wrapperClassName)}>
      <select
        ref={ref}
        className={cn(
          "focus-ring w-full appearance-none rounded border border-border bg-raised py-0.5 pl-2 pr-6 text-[11px] text-text-primary transition-colors hover:border-accent disabled:opacity-40",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-1.5 text-[9px] text-text-muted"
      >
        ▼
      </span>
    </div>
  );
});

export default Select;
