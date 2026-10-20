import { describe, expect, it } from "vitest";
import { FONT_OPTIONS, catalogWeights, findCatalogFamily, optionsForRole } from "./fontCatalog";

describe("fontCatalog", () => {
  it("has serif, sans, and mono families", () => {
    const cats = new Set(FONT_OPTIONS.map((o) => o.category));
    expect(cats).toEqual(new Set(["serif", "sans", "mono"]));
  });

  it("offers serif+sans for heading/body and mono for mono", () => {
    const heading = optionsForRole("heading", null).map((o) => o.value);
    expect(heading).toContain("DM Serif Display"); // serif
    expect(heading).toContain("Inter"); // sans
    expect(heading).not.toContain("JetBrains Mono"); // mono excluded
    expect(optionsForRole("mono", null).map((o) => o.value)).toContain("JetBrains Mono");
  });

  it("puts a Default empty option first", () => {
    expect(optionsForRole("body", null)[0]).toEqual({ value: "", label: "Default" });
  });

  it("preserves a stored non-catalog value as a (current) option", () => {
    const opts = optionsForRole("heading", "Comic Sans");
    expect(opts.at(-1)).toEqual({ value: "Comic Sans", label: "Comic Sans (current)" });
  });

  it("does not duplicate a catalog value into (current)", () => {
    expect(optionsForRole("heading", "Inter").filter((o) => o.value === "Inter")).toHaveLength(1);
  });

  it("appends uploaded font families to every role", () => {
    const opts = optionsForRole("heading", null, ["Acme Sans"]);
    expect(opts.map((o) => o.value)).toContain("Acme Sans");
    expect(optionsForRole("mono", null, ["Acme Sans"]).map((o) => o.value)).toContain("Acme Sans");
  });

  it("matches a family name case-insensitively", () => {
    expect(findCatalogFamily("inter")).toBe("Inter");
    expect(findCatalogFamily("Unknown Face")).toBeNull();
    expect(findCatalogFamily(null)).toBeNull();
  });
});

describe("catalog weights", () => {
  it("lists the weights each curated family really ships (fontsource), always with 400", () => {
    for (const o of FONT_OPTIONS) expect(o.weights).toContain(400);
    expect(catalogWeights("DM Serif Display")).toEqual([400]);
    expect(catalogWeights("Lora")).toEqual([400, 500, 600, 700]);
    expect(catalogWeights("Acme Sans")).toBeNull();
  });
});
