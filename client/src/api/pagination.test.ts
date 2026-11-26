import { describe, expect, it } from "vitest";
import { flattenPages } from "./pagination";

describe("flattenPages", () => {
  it("concatenates page items in order", () => {
    const data = { pages: [{ items: [1, 2] }, { items: [3] }] };
    expect(flattenPages(data)).toEqual([1, 2, 3]);
  });
  it("returns [] for undefined data", () => {
    expect(flattenPages<number>(undefined)).toEqual([]);
  });
});
