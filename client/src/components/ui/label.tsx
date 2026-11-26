import * as React from "react";
import { cn } from "@/lib/utils";

/** Form label — always above the field (DESIGN.md §4: never placeholder-only). */
export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label ref={ref} className={cn("mb-1.5 block eyebrow text-[11px]", className)} {...props} />
));
Label.displayName = "Label";
