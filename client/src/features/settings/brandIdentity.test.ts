import { zodResolver } from "@hookform/resolvers/zod";
import { describe, expect, it } from "vitest";
import { findCatalogFamily } from "@/styles/fontCatalog";
import type { BrandExtract } from "@/types";
import { makeBrandProfile } from "@/test/factories";
import { brandSchema, buildBrandProfile, proposalToForm, toForm } from "./brandIdentity";

const BRAND = makeBrandProfile({
  colors: [
    { name: "Forest", hex: "#1C3A2E", role: "primary" },
    { name: "Clay", hex: "#C98A3D", role: "accent" },
  ],
  accent_hex: "#C98A3D",
  fonts: { heading: "Fraunces", body: "Inter", mono: null },
  logo: { storage_key: "ws/images/1/logo.png", url: "/api/workspaces/ws/images/file/1/logo.png" },
  voice_summary: "Calm, precise.",
});

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

  it("keeps only catalog fonts, in canonical spelling (QA-14)", () => {
    const out = proposalToForm({
      ...PROPOSAL,
      fonts: { heading: "Classic serif (e.g. Freight Display)", body: "inter", mono: null },
    });
    expect(out.fonts).toEqual({ heading: "", body: "Inter", mono: "" });
  });

  it("keeps each role to its own font categories", () => {
    const out = proposalToForm({
      ...PROPOSAL,
      fonts: { heading: "JetBrains Mono", body: "Inter", mono: "Lora" },
    });
    expect(out.fonts).toEqual({ heading: "", body: "Inter", mono: "" });
  });

  it("produces a form patch the schema accepts", () => {
    const base = toForm(makeBrandProfile());
    const merged = { ...base, ...proposalToForm(PROPOSAL), accent_hex: "" };
    expect(brandSchema.safeParse(merged).success).toBe(true);
  });
});

describe("proposalToForm font snapping", () => {
  it("snaps a proposed font name to the catalog casing", () => {
    const form = proposalToForm({
      colors: [],
      voice_summary: null,
      fonts: { heading: "inter", body: "playfair display", mono: null },
    });
    expect(form.fonts.heading).toBe("Inter");
    expect(form.fonts.body).toBe("Playfair Display");
  });

  it("drops an unknown proposed font rather than applying it (DECISIONS #34)", () => {
    const form = proposalToForm({
      colors: [],
      voice_summary: null,
      fonts: { heading: "Some Custom Face", body: null, mono: null },
    });
    expect(form.fonts.heading).toBe("");
    expect(findCatalogFamily("Some Custom Face")).toBeNull();
  });
});

describe("brand form validation through the form resolver", () => {
  // The editor validates with zodResolver(brandSchema); this pins the zod and
  // @hookform/resolvers majors together: each error lands on its field.
  const resolve = (values: unknown) =>
    zodResolver(brandSchema)(values as never, undefined, {
      fields: {},
      shouldUseNativeValidation: false,
    });

  it("passes a valid form through, with color names trimmed", async () => {
    const form = {
      ...toForm(BRAND),
      colors: [{ name: " Forest ", hex: "#1C3A2E", role: "primary" }],
    };
    const result = await resolve({ ...form, accent_hex: "#1C3A2E" });
    expect(result.errors).toEqual({});
    expect((result.values as { colors: { name: string }[] }).colors[0].name).toBe("Forest");
  });

  it("puts each message on its own field", async () => {
    const result = await resolve({
      ...toForm(BRAND),
      colors: [{ name: "  ", hex: "#12ZZ45", role: "primary" }],
      accent_hex: "#C98A3D",
    });
    const errors = result.errors as Record<string, unknown> & {
      colors?: { name?: { message?: string }; hex?: { message?: string } }[];
      accent_hex?: { message?: string };
    };
    expect(errors.colors?.[0]?.name?.message).toBe("Name required");
    expect(errors.colors?.[0]?.hex?.message).toBe("Hex like #1C3A2E");
    expect(errors.accent_hex?.message).toBe("Accent must be one of the palette colors.");
  });
});
