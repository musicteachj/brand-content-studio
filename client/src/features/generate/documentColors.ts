// Brand color resolution for the document preview. Mirrors the server's
// `document_service._brand_colors` exactly so the on-screen preview reads like
// the generated .docx / PDF (preview == file by construction). The ink/muted
// values are the document's own neutral text colors (a real document is dark
// text on white paper, theme-independent) — not Folio app tokens (DESIGN §7).
import type { BrandProfile } from "@/types";

const INK = "#1A1D21";
const MUTED = "#6C737A";
const FALLBACK_PRIMARY = "#1A1D21";

export interface DocColors {
  primary: string;
  accent: string;
  ink: string;
  muted: string;
}

export function documentColors(brand: BrandProfile): DocColors {
  const byRole: Partial<Record<string, string>> = {};
  let first: string | undefined;
  for (const c of brand.colors) {
    if (c.hex) {
      if (!(c.role in byRole)) byRole[c.role] = c.hex;
      first ??= c.hex;
    }
  }
  // Falsy (not nullish) fallbacks to mirror the server's `or` chain exactly — an
  // empty-string hex must fall through, so the preview matches the rendered file.
  const primary = byRole.primary || first || FALLBACK_PRIMARY;
  const accent = brand.accent_hex || byRole.accent || byRole.secondary || primary;
  return { primary, accent, ink: INK, muted: MUTED };
}
