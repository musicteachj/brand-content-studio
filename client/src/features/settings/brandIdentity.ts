import { z } from "zod";
import { findCatalogFamily } from "@/styles/fontCatalog";
import type { BrandExtract, BrandProfile, BrandProfilePatch, ColorRole } from "@/types";

// Pure brand-profile form schema + mappers (kept out of the component file so
// fast-refresh stays component-only, and so they're unit-testable).
export const ROLES: ColorRole[] = ["primary", "secondary", "neutral", "accent"];
export const HEX_RE = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/;

export const brandSchema = z
  .object({
    colors: z.array(
      z.object({
        name: z.string().trim().min(1, "Name required"),
        hex: z.string().regex(HEX_RE, "Hex like #1C3A2E"),
        role: z.enum(["primary", "secondary", "neutral", "accent"]),
      }),
    ),
    fonts: z.object({ heading: z.string(), body: z.string(), mono: z.string() }),
    voice_summary: z.string(),
    accent_hex: z.string(),
  })
  .superRefine((val, ctx) => {
    if (
      val.accent_hex &&
      !val.colors.some((c) => c.hex.toLowerCase() === val.accent_hex.toLowerCase())
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["accent_hex"],
        message: "Accent must be one of the palette colors.",
      });
    }
  });

export type BrandForm = z.infer<typeof brandSchema>;

export function toForm(brand: BrandProfile): BrandForm {
  return {
    colors: brand.colors.map((c) => ({ name: c.name, hex: c.hex, role: c.role })),
    fonts: {
      heading: brand.fonts.heading ?? "",
      body: brand.fonts.body ?? "",
      mono: brand.fonts.mono ?? "",
    },
    voice_summary: brand.voice_summary ?? "",
    accent_hex: brand.accent_hex ?? "",
  };
}

/** Map an extracted proposal (Phase 4c) into the form-field shape so it can be
 *  applied into the editor for review. Colors/fonts/voice only — accent and logo
 *  are untouched. Applying replaces the palette + fonts + voice; the user still
 *  reviews and explicitly Saves (the proposal is never persisted directly). */
export function proposalToForm(
  p: BrandExtract,
): Pick<BrandForm, "colors" | "fonts" | "voice_summary"> {
  return {
    colors: p.colors.map((c) => ({ name: c.name, hex: c.hex, role: c.role })),
    fonts: {
      // Only catalog families: a non-catalog proposal (e.g. a style description)
      // would be saved as a brand font the card can't load (QA-14).
      heading: findCatalogFamily(p.fonts.heading, "heading") ?? "",
      body: findCatalogFamily(p.fonts.body, "body") ?? "",
      mono: findCatalogFamily(p.fonts.mono, "mono") ?? "",
    },
    voice_summary: p.voice_summary ?? "",
  };
}

/** Map the edit form back to the brand PATCH payload. The PATCH replaces the
 *  profile whole, so this carries the logo through (it's persisted separately)
 *  and normalizes empty strings to null. The sub-collections are re-hydrated
 *  server-side — see BrandProfilePatch. */
export function buildBrandProfile(
  values: BrandForm,
  logo: BrandProfile["logo"],
): BrandProfilePatch {
  return {
    colors: values.colors.map((c) => ({ name: c.name.trim(), hex: c.hex, role: c.role })),
    accent_hex: values.accent_hex || null,
    fonts: {
      heading: values.fonts.heading.trim() || null,
      body: values.fonts.body.trim() || null,
      mono: values.fonts.mono.trim() || null,
    },
    logo,
    voice_summary: values.voice_summary.trim() || null,
  };
}
