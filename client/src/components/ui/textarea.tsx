import * as React from "react";
import { cn } from "@/lib/utils";

/** Folio textarea (DESIGN.md §4): outlined, focus = 2px ring. */
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-sm border border-border bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-foreground transition-shadow placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";
