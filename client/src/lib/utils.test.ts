import { describe, expect, it } from "vitest";
import { cn } from "./utils";

// cn() knows the project's own theme values (the @theme block in index.css), so a
// later class of the same kind wins and nothing of another kind is dropped.
describe("cn with the custom theme", () => {
  it.each([
    ["shadow-light shadow-none", "shadow-none"],
    ["shadow-light shadow-medium", "shadow-medium"],
    ["tracking-eyebrow tracking-heading", "tracking-heading"],
    ["z-modal z-toast", "z-toast"],
    ["animate-fade-in animate-fade-in-up", "animate-fade-in-up"],
    ["text-2xs text-3xs", "text-3xs"],
  ])("%s resolves to %s", (input, want) => {
    expect(cn(input)).toBe(want);
  });

  it.each([["text-2xs text-muted-foreground"], ["eyebrow text-3xs"], ["shadow-light ring-2"]])(
    "keeps both classes in %s",
    (input) => {
      expect(cn(input)).toBe(input);
    },
  );
});
