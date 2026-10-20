import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// The project's own theme values (the @theme block in index.css), so conflicting
// classes resolve: `shadow-none` overrides `shadow-light`, a later `z-*` wins.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ["2xs", "3xs"],
      tracking: ["eyebrow", "heading", "display"],
      shadow: ["light", "medium", "heavy", "accent", "preview"],
      animate: ["fade-in-up", "slide-in-right", "fade-in"],
    },
    classGroups: {
      z: [{ z: ["header", "dropdown", "drawer", "picker", "modal", "toast"] }],
    },
  },
});

/** shadcn class-merge helper. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
