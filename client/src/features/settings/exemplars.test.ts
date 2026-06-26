import { describe, expect, it } from "vitest";
import { canAddExemplar, MAX_EXEMPLARS } from "./exemplars";

describe("exemplar cap (Phase 4c)", () => {
  it("allows adding below the cap for a non-demo user", () => {
    expect(canAddExemplar(0, false)).toBe(true);
    expect(canAddExemplar(MAX_EXEMPLARS - 1, false)).toBe(true);
  });
  it("blocks at the cap", () => {
    expect(canAddExemplar(MAX_EXEMPLARS, false)).toBe(false);
  });
  it("blocks for the demo user regardless of count", () => {
    expect(canAddExemplar(0, true)).toBe(false);
  });
});
