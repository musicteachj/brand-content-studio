// @vitest-environment node
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";
import satori from "satori";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadBrandFontBuffers,
  SCRIPTS_FAMILY,
  SYMBOLS_FAMILY,
  type SatoriFont,
} from "./brandFonts";

// QA-17, end to end: the production font list from loadBrandFontBuffers (bundled
// assets served from disk) through the real Satori renderer. Without the glyph
// fallbacks, ₂/≥/→ render as placeholders; with them, as real outlines.
const ASSETS = fileURLToPath(new URL("../assets/fonts/", import.meta.url));

afterEach(() => vi.unstubAllGlobals());

async function productionFonts(): Promise<SatoriFont[]> {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const data = readFileSync(ASSETS + basename(url.split("?")[0]));
      return {
        ok: true,
        status: 200,
        arrayBuffer: async () =>
          data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength),
      };
    }),
  );
  // No brand fonts set: the bundled Lora fallback, plus the glyph fallbacks.
  return loadBrandFontBuffers({ heading: null, body: null, mono: null }, []);
}

const isGlyphFallback = (f: SatoriFont) => f.name === SCRIPTS_FAMILY || f.name === SYMBOLS_FAMILY;

async function svg(text: string, fonts: SatoriFont[]): Promise<string> {
  const family = fonts.find((f) => !isGlyphFallback(f))!.name;
  return satori(<div style={{ display: "flex", fontFamily: family, fontSize: 64 }}>{text}</div>, {
    width: 900,
    height: 120,
    fonts,
  });
}

const outline = (s: string) => (s.match(/ d="([^"]*)"/g) ?? []).join("").length;

describe("card glyph coverage (QA-17)", () => {
  it("draws subscripts, superscripts, and common symbols", async () => {
    const fonts = await productionFonts();
    const brandOnly = fonts.filter((f) => !isGlyphFallback(f));
    for (const text of ["CO₂", "10⁵", "≥ 40%", "net zero →"]) {
      expect(outline(await svg(text, fonts))).toBeGreaterThan(outline(await svg(text, brandOnly)));
    }
  });

  it("leaves text the brand face covers byte-identical", async () => {
    const fonts = await productionFonts();
    const brandOnly = fonts.filter((f) => !isGlyphFallback(f));
    const text = "Carbon stored: 110 kg × 2 ± 5%";
    expect(await svg(text, fonts)).toBe(await svg(text, brandOnly));
  });
});
