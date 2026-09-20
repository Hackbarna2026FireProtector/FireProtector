/**
 * Card — the panel chrome every section of the command centre repeats.
 *
 * Named after shadcn's Card so the call sites read the same, but shaped to
 * what this app actually stacks: a padded `<section>` whose title is the small
 * uppercase label running down the right-hand rail.
 */

import type { HTMLAttributes } from "react";

import { cn } from "./cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("p-3", className)} {...props} />;
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-2 flex items-center gap-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        "text-xs font-semibold uppercase tracking-wider text-text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn(className)} {...props} />;
}

/** The "nothing selected / nothing generated yet" line inside a panel. */
export function CardEmpty({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-text-muted", className)} {...props} />;
}
