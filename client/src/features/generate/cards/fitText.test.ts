import { describe, expect, it } from "vitest";
import { fitTextSize } from "./fitText";

// Photo-led headline box (cardElement HEADLINE_FIT["photo-led"]).
const SPEC = { max: 80, min: 46, lineHeight: 1.04, boxWidth: 904, boxHeight: 470 };

describe("fitTextSize", () => {
  it("keeps the design size for short copy that fits", () => {
    expect(fitTextSize({ ...SPEC, text: "Carbon, locked in" })).toBe(80);
  });

  it("returns the max for empty text", () => {
    expect(fitTextSize({ ...SPEC, text: "" })).toBe(80);
  });

  it("shrinks an over-long headline below the design size", () => {
    const long =
      "Hempcrete sequesters atmospheric carbon throughout the entire service life of the building envelope and beyond";
    const size = fitTextSize({ ...SPEC, text: long });
    expect(size).toBeLessThan(80);
    expect(size).toBeGreaterThanOrEqual(46);
  });

  it("never returns below the min, even for absurd lengths", () => {
    const huge = "word ".repeat(400);
    expect(fitTextSize({ ...SPEC, text: huge })).toBe(46);
  });

  it("shrinks monotonically as text grows", () => {
    const short = fitTextSize({ ...SPEC, text: "Short headline here" });
    const medium = fitTextSize({
      ...SPEC,
      text: "A noticeably longer headline that wraps across a couple of lines",
    });
    const long = fitTextSize({
      ...SPEC,
      text: "An even longer headline that should clearly need several lines to lay out at the design size and then some",
    });
    expect(short).toBeGreaterThanOrEqual(medium);
    expect(medium).toBeGreaterThanOrEqual(long);
  });

  it("shrinks for a single unbreakable word wider than the box", () => {
    const size = fitTextSize({ ...SPEC, text: "Supercalifragilisticexpialidocious".repeat(2) });
    expect(size).toBeLessThan(80);
  });
});
