import { describe, expect, it } from "vitest";
import { emptyValues, mergeFilled } from "./templateForm";

describe("template fill form (Phase 5)", () => {
  it("initializes an empty value per placeholder", () => {
    expect(emptyValues(["title", "body"])).toEqual({ title: "", body: "" });
  });
  it("merges AI-filled values only for known placeholders", () => {
    const merged = mergeFilled(["title", "body"], { title: "Hi", extra: "x" });
    expect(merged).toEqual({ title: "Hi", body: "" });
  });
});
