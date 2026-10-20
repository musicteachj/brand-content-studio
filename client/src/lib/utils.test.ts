import { readFileSync } from "node:fs";
import path from "node:path";
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

// The merge config in utils.ts repeats the @theme names by hand; this fails when a
// new --shadow-*, --tracking-*, --z-index-*, or --animate-* lands in index.css
// without being registered (cn() would then keep both conflicting classes).
describe("cn knows every custom @theme value", () => {
  const css = readFileSync(path.resolve(process.cwd(), "src/index.css"), "utf8");
  const theme = css.slice(css.indexOf("@theme"), css.indexOf("@keyframes"));
  const names = (prefix: string) =>
    [...theme.matchAll(new RegExp(`--${prefix}-([a-z0-9-]+):`, "g"))].map((m) => m[1]);

  const groups: [string, string, string][] = [
    ["shadow", "shadow", "shadow-none"],
    ["tracking", "tracking", "tracking-normal"],
    ["z-index", "z", "z-10"],
    ["animate", "animate", "animate-none"],
  ];
  it.each(groups)("every --%s-* is registered", (prefix, utility, later) => {
    const found = names(prefix);
    expect(found.length).toBeGreaterThan(0);
    for (const n of found) expect(cn(`${utility}-${n} ${later}`)).toBe(later);
  });
});
