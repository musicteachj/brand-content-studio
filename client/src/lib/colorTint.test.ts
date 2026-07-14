import { afterEach, describe, expect, it } from "vitest";
import { applyAccentTint } from "./colorTint";

// Read a token off the document root the way the stylesheet does.
const token = (name: string) => document.documentElement.style.getPropertyValue(name).trim();

afterEach(() => applyAccentTint(null));

describe("applyAccentTint — accent foreground by luminance (A11Y-02)", () => {
  // The regression: a bright accent whose HSL lightness is <=60 but which needs
  // DARK text, not white. Pure yellow is the canonical trap (white = 1.07:1).
  it.each([
    ["#FFFF00", "214 12% 12%"], // yellow -> dark ink
    ["#00FF00", "214 12% 12%"], // green -> dark ink
    ["#00FFFF", "214 12% 12%"], // cyan -> dark ink
    ["#FF9900", "214 12% 12%"], // orange -> dark ink
    ["#1C3A2E", "0 0% 100%"], // deep forest -> white
    ["#C2185B", "0 0% 100%"], // Folio magenta -> white
  ])("picks the higher-contrast ink for %s", (hex, expected) => {
    applyAccentTint(hex);
    expect(token("--accent-foreground")).toBe(expected);
  });

  it("clamps the focus ring's lightness so a pale accent stays visible", () => {
    applyAccentTint("#F4F1E9"); // cream — would be an invisible ring unclamped
    const l = Number(token("--ring").split(" ")[2].replace("%", ""));
    expect(l).toBeLessThanOrEqual(55);
  });

  it("clears the overrides when passed null", () => {
    applyAccentTint("#C2185B");
    applyAccentTint(null);
    expect(token("--accent-foreground")).toBe("");
    expect(token("--accent")).toBe("");
  });

  it("ignores an invalid hex without setting any token", () => {
    applyAccentTint("not-a-color");
    expect(token("--accent")).toBe("");
  });
});
