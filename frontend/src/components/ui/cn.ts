/**
 * Class-name joiner.
 *
 * shadcn/ui builds this out of `clsx` + `tailwind-merge`. This is the
 * zero-dependency stand-in, so it joins but does *not* resolve conflicts: pass
 * `p-4` to a component whose base is `p-2` and both survive into the class
 * list, leaving the winner to stylesheet order rather than intent. The variant
 * maps in this folder are written around that — they avoid setting properties a
 * caller is likely to override, and callers override by choosing a variant
 * rather than by fighting the base classes.
 *
 * Swapping in the real `cn()` later means installing the two packages and
 * replacing this file; nothing else in the folder has to change.
 */
export type ClassValue = string | false | null | undefined;

export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(" ");
}
