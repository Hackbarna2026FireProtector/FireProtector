/** Button — shadcn-shaped variants over the project's dark token set. */

import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "./cn";

const VARIANTS = {
  default: "border-border bg-raised text-text-primary hover:border-accent",
  accent: "border-accent/50 bg-accent/10 text-accent hover:bg-accent/20",
  ghost: "border-transparent text-text-secondary hover:bg-raised hover:text-text-primary",
  outline: "border-border text-text-secondary hover:border-accent hover:text-text-primary",
} as const;

const SIZES = {
  sm: "px-2 py-0.5 text-[11px]",
  md: "px-3 py-1.5 text-xs",
  icon: "h-7 w-8 text-sm",
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "sm", className, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "focus-ring inline-flex items-center justify-center gap-1.5 rounded border font-semibold transition-colors disabled:pointer-events-none disabled:opacity-40",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
});

export default Button;
