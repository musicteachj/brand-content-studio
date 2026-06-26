import { describe, expect, it } from "vitest";
import type { BrandExtract, BrandProfile } from "@/types";
import { brandSchema, buildBrandProfile, proposalToForm, toForm } from "./brandIdentity";

const BRAND: BrandProfile = {
  colors: [
    { name: "Forest", hex: "#1C3A2E", role: "primary" },
    { name: "Clay", hex: "#C98A3D", role: "accent" },
  ],
  accent_hex: "#C98A3D",
  fonts: { heading: "Fraunces", body: "Inter", mono: null },
  logo: { storage_key: "ws/images/1/logo.png", url: "/api/workspaces/ws/images/file/1/logo.png" },
  voice_summary: "Calm, precise.",
};

describe("brand identity mapping (Phase 4b)", () => {
  it("round-trips a profile, mapping null<->'' for optional fields", () => {
    const form = toForm(BRAND);
    expect(form.fonts.mono).toBe(""); // null -> ""
    const back = buildBrandProfile(form, BRAND.logo);
    expect(back.fonts.mono).toBeNull(); // "" -> null
    expect(back.colors).toEqual(BRAND.colors);
    expect(back.accent_hex).toBe("#C98A3D");
    expect(back.voice_summary).toBe("Calm, precise.");
  });

  it("preserves the logo (the PATCH replaces brand_profile whole)", () => {
    const back = buildBrandProfile(toForm(BRAND), BRAND.logo);
    expect(back.logo).toEqual(BRAND.logo);
  });

  it("normalizes blank fonts/voice/accent to null and trims color names", () => {
    const form = toForm(BRAND);
    form.fonts.heading = "  ";
    form.voice_summary = "  ";
    form.accent_hex = "";
    form.colors[0].name = "  Forest  ";
    const back = buildBrandProfile(form, null);
    expect(back.fonts.heading).toBeNull();
    expect(back.voice_summary).toBeNull();
    expect(back.accent_hex).toBeNull();
    expect(back.colors[0].name).toBe("Forest");
    expect(back.logo).toBeNull();
  });

  it("schema rejects an accent that isn't in the palette", () => {
    const form = toForm(BRAND);
    form.accent_hex = "#FF00FF";
    expect(brandSchema.safeParse(form).success).toBe(false);
  });

  it("schema rejects a malformed hex / empty color name", () => {
    const form = toForm(BRAND);
    form.colors.push({ name: "", hex: "nope", role: "secondary" });
    expect(brandSchema.safeParse(form).success).toBe(false);
  });

  it("schema accepts a valid profile (incl. empty accent)", () => {
    const form = toForm(BRAND);
    form.accent_hex = "";
    expect(brandSchema.safeParse(form).success).toBe(true);
  });
});

describe("proposalToForm (Phase 4c)", () => {
  const PROPOSAL: BrandExtract = {
    colors: [{ name: "Forest", hex: "#1C3A2E", role: "primary" }],
    voice_summary: null,
    fonts: { heading: "Fraunces", body: null, mono: null },
  };

  it("maps a proposal into form fields, null fonts/voice → ''", () => {
    const out = proposalToForm(PROPOSAL);
    expect(out.colors).toEqual([{ name: "Forest", hex: "#1C3A2E", role: "primary" }]);
    expect(out.fonts).toEqual({ heading: "Fraunces", body: "", mono: "" });
    expect(out.voice_summary).toBe("");
  });

  it("produces a form patch the schema accepts", () => {
    const base = toForm({
      colors: [],
      accent_hex: null,
      fonts: { heading: null, body: null, mono: null },
      logo: null,
      voice_summary: null,
    });
    const merged = { ...base, ...proposalToForm(PROPOSAL), accent_hex: "" };
    expect(brandSchema.safeParse(merged).success).toBe(true);
  });
});
