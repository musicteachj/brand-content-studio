import type { BrandProfile } from "@/types";

/** A complete BrandProfile for tests. Spread overrides on top of the empty
 *  defaults so that adding a field to BrandProfile breaks this file only,
 *  instead of every fixture that constructs one by hand. */
export function makeBrandProfile(overrides: Partial<BrandProfile> = {}): BrandProfile {
  return {
    colors: [],
    accent_hex: null,
    fonts: { heading: null, body: null, mono: null },
    logo: null,
    voice_summary: null,
    exemplars: [],
    brand_images: [],
    uploaded_fonts: [],
    card_presets: [],
    ...overrides,
  };
}
