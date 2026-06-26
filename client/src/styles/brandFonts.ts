// Workspace brand fonts for the card — loaded as font BUFFERS for Satori
// (ARCHITECTURE gotcha #2) and injected as @font-face for the live DOM preview.
// Both reference the SAME fontsource TTF binaries, so the DOM preview and the
// Satori export use byte-identical glyphs — preview == export by construction.
//
// App chrome (Plus Jakarta Sans / DM Mono) is never used here: the card is the
// workspace's artifact, not Folio's UI (DESIGN §7).
import type { BrandFonts } from "@/types";

export interface SatoriFont {
  name: string;
  data: ArrayBuffer;
  weight: 400 | 600 | 700;
  style: "normal";
}

// fontsource serves Google fonts as TTF (Satori cannot parse Google's default
// woff2). Stable, CORS-enabled CDN.
function ttfUrl(family: string, weight: number): string {
  const slug = family.trim().toLowerCase().replace(/\s+/g, "-");
  return `https://cdn.jsdelivr.net/fontsource/fonts/${slug}@latest/latin-${weight}-normal.ttf`;
}

// Families used by the card, with the weights the archetypes reference. A brand's
// display face often ships a single weight (e.g. DM Serif Display = 400 only), so
// missing weights are tolerated — Satori falls back to the nearest available.
const HEADING_WEIGHTS: Array<400 | 700> = [400, 700];
const BODY_WEIGHTS: Array<400 | 600 | 700> = [400, 600, 700];

export const FALLBACK_HEADING = "Georgia, serif";
export const FALLBACK_BODY = "Georgia, serif";

export function headingFamily(fonts: BrandFonts): string {
  return fonts.heading || fonts.body || "Georgia";
}
export function bodyFamily(fonts: BrandFonts): string {
  return fonts.body || fonts.heading || "Georgia";
}

interface FontReq {
  family: string;
  weight: 400 | 600 | 700;
}

function requiredFonts(fonts: BrandFonts): FontReq[] {
  const heading = headingFamily(fonts);
  const body = bodyFamily(fonts);
  const reqs: FontReq[] = [];
  for (const w of HEADING_WEIGHTS) reqs.push({ family: heading, weight: w });
  for (const w of BODY_WEIGHTS) reqs.push({ family: body, weight: w });
  // De-dupe when heading === body.
  const seen = new Set<string>();
  return reqs.filter((r) => {
    const key = `${r.family}:${r.weight}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Only successful loads are cached. A transient failure (offline, CDN 5xx) must
// not be memoized — otherwise the very first network blip would permanently break
// card preview/export until a full reload.
const bufferCache = new Map<string, ArrayBuffer>();
const inflight = new Map<string, Promise<ArrayBuffer | null>>();

async function loadBuffer(family: string, weight: number): Promise<ArrayBuffer | null> {
  const url = ttfUrl(family, weight);
  const cached = bufferCache.get(url);
  if (cached) return cached;
  let p = inflight.get(url);
  if (!p) {
    p = (async () => {
      try {
        const r = await fetch(url);
        if (!r.ok) return null; // 404 (weight not on the CDN) — a real "skip"
        const buf = await r.arrayBuffer();
        bufferCache.set(url, buf);
        return buf;
      } catch {
        return null; // transient — not cached, retried on next render
      } finally {
        inflight.delete(url);
      }
    })();
    inflight.set(url, p);
  }
  return p;
}

/** Font buffers for Satori. Weights that 404 on the CDN are skipped. */
export async function loadBrandFontBuffers(fonts: BrandFonts): Promise<SatoriFont[]> {
  const out = await Promise.all(
    requiredFonts(fonts).map(async (req) => {
      const data = await loadBuffer(req.family, req.weight);
      return data
        ? ({ name: req.family, data, weight: req.weight, style: "normal" } as SatoriFont)
        : null;
    }),
  );
  return out.filter((f): f is SatoriFont => f !== null);
}

const injected = new Set<string>();

/** Inject @font-face for the DOM live preview so it renders in the workspace
 *  fonts (not the app's), matching the Satori export. Idempotent per family. */
export function injectBrandFontFaces(fonts: BrandFonts): void {
  if (typeof document === "undefined") return;
  for (const req of requiredFonts(fonts)) {
    const key = `${req.family}:${req.weight}`;
    if (injected.has(key)) continue;
    injected.add(key);
    const style = document.createElement("style");
    style.dataset.brandFont = key;
    style.textContent = `@font-face{font-family:"${req.family}";font-style:normal;font-weight:${req.weight};font-display:swap;src:url("${ttfUrl(
      req.family,
      req.weight,
    )}") format("truetype");}`;
    document.head.appendChild(style);
  }
}
