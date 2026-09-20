/** Checkbox — native input, sized and tinted to match the rest of the chrome. */

import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "./cn";

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn(
        "focus-ring h-3.5 w-3.5 shrink-0 cursor-pointer rounded border-border accent-accent disabled:cursor-not-allowed disabled:opacity-40",
        className,
      )}
      {...props}
    />
  );
});

export default Checkbox;
