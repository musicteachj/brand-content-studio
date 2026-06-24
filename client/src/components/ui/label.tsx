import * as React from "react";
import { cn } from "@/lib/utils";

/** Form label — always above the field (DESIGN.md §4: never placeholder-only). */
export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={cn(
      "mb-1.5 block font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground",
      className,
    )}
    {...props}
  />
));
Label.displayName = "Label";
