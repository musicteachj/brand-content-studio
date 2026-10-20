// Workspace brand fonts for the card — loaded as font BUFFERS for Satori
// (ARCHITECTURE gotcha #2) and injected as @font-face for the live DOM preview.
// Both reference the SAME fontsource TTF binaries, so the DOM preview and the
// Satori export use byte-identical glyphs — preview == export by construction.
//
// App chrome (Plus Jakarta Sans / DM Mono) is never used here: the card is the
// workspace's artifact, not Folio's UI (DESIGN §7).
import scriptsRegularUrl from "@/assets/fonts/folio-card-scripts-400.ttf?url";
import scriptsBoldUrl from "@/assets/fonts/folio-card-scripts-700.ttf?url";
import symbolsUrl from "@/assets/fonts/folio-card-symbols-400.ttf?url";
import loraBoldUrl from "@/assets/fonts/lora-latin-700-normal.ttf?url";
import loraRegularUrl from "@/assets/fonts/lora-latin-400-normal.ttf?url";
import { useAuthStore } from "@/stores/auth";
import { catalogWeights } from "@/styles/fontCatalog";
import type { BrandFonts, UploadedFont } from "@/types";

export interface SatoriFont {
  name: string;
  data: ArrayBuffer;
  weight: 400 | 600 | 700;
  style: "normal";
}

// fontsource serves Google fonts as TTF (Satori cannot parse Google's default
// woff2). Stable, CORS-enabled CDN.
function ttfUrl(family: string, weight: number): string {
  // Collapse every non-alphanumeric run to a hyphen (not just whitespace), so a
  // crafted family can't smuggle `"`/`)` into the url() descriptor addFontFace
  // builds. Legit fontsource families (letters + spaces) slug identically.
  const slug = family
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `https://cdn.jsdelivr.net/fontsource/fonts/${slug}@latest/latin-${weight}-normal.ttf`;
}

// Families used by the card, with the weights the archetypes reference. A brand's
// display face often ships a single weight (e.g. DM Serif Display = 400 only): a
// curated family is only asked for the weights it has, and for any other family a
// missing weight is tolerated (Satori falls back to the nearest available).
const HEADING_WEIGHTS: Array<400 | 700> = [400, 700];
const BODY_WEIGHTS: Array<400 | 600 | 700> = [400, 600, 700];

// The card's bundled font (Lora, OFL; see src/assets/fonts). It's the default when a
// workspace sets no brand font, and the stand-in for a family the CDN doesn't have
// (a system font like Georgia, a typo, a legacy free-text value), so a card can
// always render and export. A private name, so the default never collides with a
// real family.
export const FALLBACK_FAMILY = "Folio Card Serif";

// Documents keep their own default: the server renders an unset font as a serif
// base face (PDF) or leaves it to Word (.docx), so the preview shouldn't show Lora.
export const DOCUMENT_DEFAULT_FAMILY = "Georgia";

function fallbackUrl(weight: number): string {
  return weight >= 600 ? loraBoldUrl : loraRegularUrl;
}

// Glyph fallbacks (QA-17). The brand fonts are fontsource Latin subsets, so
// characters outside Latin drew a NO GLYPH box in the export ("CO₂" above all).
// These small bundled faces (OFL; see src/assets/fonts) ride last in Satori's
// font list, which it falls back through per glyph, so they're only used where
// the brand face has no glyph. The DOM preview gets the same faces through
// `unicode-range` (see injectFamily), so preview == export holds.
export const SCRIPTS_FAMILY = "Folio Card Scripts"; // ⁰ ⁴-⁹ ₀-₉ and script signs (Noto Serif)
export const SYMBOLS_FAMILY = "Folio Card Symbols"; // arrows, ≈ ≠ ≤ ≥ and friends, ✓ (Noto Sans Math)

interface GlyphFallback {
  family: string;
  weight: 400 | 700;
  url: string;
  unicodeRange: string;
}

const SCRIPTS_RANGE = "U+2070-209F";
const SYMBOLS_RANGE =
  "U+2190-2199, U+21D2, U+21D4, U+2211, U+2213, U+221A, U+221D-221E, U+2234, U+2248, U+2260-2261, U+2264-2265, U+226A-226B, U+2713";

const GLYPH_FALLBACKS: GlyphFallback[] = [
  { family: SCRIPTS_FAMILY, weight: 400, url: scriptsRegularUrl, unicodeRange: SCRIPTS_RANGE },
  { family: SCRIPTS_FAMILY, weight: 700, url: scriptsBoldUrl, unicodeRange: SCRIPTS_RANGE },
  { family: SYMBOLS_FAMILY, weight: 400, url: symbolsUrl, unicodeRange: SYMBOLS_RANGE },
];

export function headingFamily(fonts: BrandFonts, fallback: string = FALLBACK_FAMILY): string {
  return fonts.heading || fonts.body || fallback;
}
export function bodyFamily(fonts: BrandFonts, fallback: string = FALLBACK_FAMILY): string {
  return fonts.body || fonts.heading || fallback;
}

interface FontReq {
  family: string;
  weight: 400 | 600 | 700;
}

function requiredFonts(fonts: BrandFonts, uploaded: UploadedFont[]): FontReq[] {
  const heading = headingFamily(fonts);
  const body = bodyFamily(fonts);
  const reqs: FontReq[] = [];
  // An uploaded font serves its one file at every weight, so it's never filtered,
  // even if it shares a curated family's name.
  const has = (family: string, weight: number) =>
    uploadedUrl(family, uploaded) !== null || (catalogWeights(family)?.includes(weight) ?? true);
  for (const w of HEADING_WEIGHTS) if (has(heading, w)) reqs.push({ family: heading, weight: w });
  for (const w of BODY_WEIGHTS) if (has(body, w)) reqs.push({ family: body, weight: w });
  // De-dupe when heading === body.
  const seen = new Set<string>();
  return reqs.filter((r) => {
    const key = `${r.family}:${r.weight}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// A font load is the bytes, MISSING (the CDN answered 404: permanent, so cached),
// or null (a transient failure: offline, CDN 5xx). Transient failures are never
// memoized, otherwise the first network blip would break preview/export until a
// full reload, and they never trigger the fallback, so a blip can't silently swap
// a real brand font for Lora.
const MISSING = "missing" as const;
type FontLoad = ArrayBuffer | typeof MISSING | null;

const bufferCache = new Map<string, ArrayBuffer>();
const missCache = new Set<string>();
const cdnInflight = new Map<string, Promise<FontLoad>>();
const inflight = new Map<string, Promise<ArrayBuffer | null>>();

async function loadBuffer(family: string, weight: number): Promise<FontLoad> {
  const url = ttfUrl(family, weight);
  const cached = bufferCache.get(url);
  if (cached) return cached;
  if (missCache.has(url)) return MISSING;
  let p = cdnInflight.get(url);
  if (!p) {
    p = (async (): Promise<FontLoad> => {
      try {
        const r = await fetch(url);
        if (r.status === 404) {
          missCache.add(url);
          return MISSING;
        }
        if (!r.ok) return null;
        const buf = await r.arrayBuffer();
        bufferCache.set(url, buf);
        return buf;
      } catch {
        return null;
      } finally {
        cdnInflight.delete(url);
      }
    })();
    cdnInflight.set(url, p);
  }
  return p;
}

// ---------------------------------------------------------------------------
// Uploaded brand fonts (.ttf) — a source-aware path layered over the CDN one.
// The user-given family name is the handle everywhere; an uploaded family's
// bytes come from its own (same-origin, auth-gated) url instead of the CDN.
// ---------------------------------------------------------------------------
function uploadedUrl(family: string, uploaded: UploadedFont[]): string | null {
  return uploaded.find((f) => f.family === family)?.url ?? null;
}

async function fetchFontBytes(url: string, auth = true): Promise<ArrayBuffer | null> {
  const cached = bufferCache.get(url);
  if (cached) return cached;
  // Dedup concurrent requests for the same url (Satori needs an uploaded family
  // at several weights → the same bytes), mirroring the CDN path's `inflight`.
  let p = inflight.get(url);
  if (!p) {
    p = (async () => {
      const sameOrigin = url.startsWith("/") && !url.startsWith("//");
      const token = auth ? useAuthStore.getState().token : null;
      try {
        const resp = await fetch(url, {
          headers: sameOrigin && token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!resp.ok) return null;
        const buf = await resp.arrayBuffer();
        bufferCache.set(url, buf);
        return buf;
      } catch {
        return null;
      } finally {
        inflight.delete(url);
      }
    })();
    inflight.set(url, p);
  }
  return p;
}

function satoriFont(name: string, weight: 400 | 600 | 700, data: FontLoad): SatoriFont | null {
  return data instanceof ArrayBuffer ? { name, data, weight, style: "normal" } : null;
}

/** One source decision for preview and export: the bundled fallback, an uploaded
 *  family's own (auth-gated) bytes, or the CDN. */
function loadFace(family: string, weight: number, uploaded: UploadedFont[]): Promise<FontLoad> {
  if (family === FALLBACK_FAMILY) return fetchFontBytes(fallbackUrl(weight), false);
  const up = uploadedUrl(family, uploaded);
  return up ? fetchFontBytes(up) : loadBuffer(family, weight);
}

/** A family is missing when its regular (400) cut is a definite 404. A family
 *  that has its regular cut but lacks a bold (single-weight display faces) is
 *  real, and a transient failure proves nothing, so neither counts. */
async function familyIsMissing(family: string, uploaded: UploadedFont[]): Promise<boolean> {
  return (await loadFace(family, 400, uploaded)) === MISSING;
}

/** Font buffers for Satori. A missing family gets the bundled fallback at every
 *  weight, under its own name, so the card still renders and exports. Otherwise
 *  a weight that 404s is skipped (Satori uses the nearest one), and a transient
 *  failure leaves the list short so the export reports a retryable error. */
export async function loadBrandFontBuffers(
  fonts: BrandFonts,
  uploaded: UploadedFont[] = [],
): Promise<SatoriFont[]> {
  const reqs = requiredFonts(fonts, uploaded);
  // Same-origin assets: start them alongside the brand fonts, not after.
  const glyphBytes = Promise.all(GLYPH_FALLBACKS.map((g) => fetchFontBytes(g.url, false)));
  const loaded = await Promise.all(reqs.map((r) => loadFace(r.family, r.weight, uploaded)));
  const missing = new Set(
    reqs.filter((r, i) => r.weight === 400 && loaded[i] === MISSING).map((r) => r.family),
  );
  const brand = await Promise.all(
    reqs.map(async (req, i) =>
      satoriFont(
        req.family,
        req.weight,
        missing.has(req.family) ? await fetchFontBytes(fallbackUrl(req.weight), false) : loaded[i],
      ),
    ),
  );
  const glyphs = (await glyphBytes).map((data, i) =>
    satoriFont(GLYPH_FALLBACKS[i].family, GLYPH_FALLBACKS[i].weight, data),
  );
  const brandFaces = brand.filter((f): f is SatoriFont => f !== null);
  // An empty list surfaces the retryable "couldn't load fonts" error. A missing
  // glyph face counts too: it's a same-origin asset, so failing means a network
  // problem, and exporting without it would bring the NO GLYPH boxes back.
  if (brandFaces.length === 0 || glyphs.includes(null)) return [];
  return [...brandFaces, ...(glyphs as SatoriFont[])];
}

const injected = new Set<string>();

function addFontFace(
  family: string,
  weight: number,
  source: string | ArrayBuffer,
  onLoadError?: () => void,
  unicodeRange?: string,
): void {
  // Register via the CSSOM FontFace API rather than interpolating `family`/`src`
  // into a <style> string. The constructor treats `family` as data (quoting it
  // internally), so a crafted family name — `"`, `}`, `</style>` — cannot break
  // out of the declaration. `source` is either the raw uploaded font bytes
  // (auth-gated) or an app-controlled CDN URL.
  if (typeof FontFace === "undefined") return; // non-browser env (SSR / jsdom)
  const key = `${family}:${weight}`;
  try {
    const src = typeof source === "string" ? `url("${source}")` : source;
    const face = new FontFace(family, src, {
      weight: String(weight),
      style: "normal",
      display: "swap",
      ...(unicodeRange ? { unicodeRange } : {}),
    });
    document.fonts.add(face);
    void face.load().catch(() => {
      document.fonts.delete(face);
      if (onLoadError) {
        onLoadError();
      } else {
        // A transient failure must be retryable, so clear the dedup key too
        // (injectFamily marked it before calling us).
        injected.delete(key);
      }
    });
  } catch {
    injected.delete(key); // invalid descriptor — drop the key so a later call retries
  }
}

/** The glyph fallbacks, registered under the brand family with a `unicode-range`,
 *  so the browser reaches them per character exactly as Satori does. Added before
 *  the brand face, so for a character both cover the brand's own glyph wins. */
function injectGlyphFallbacks(family: string, weight: number): void {
  const key = `${family}:${weight}:glyphs`;
  if (injected.has(key)) return;
  injected.add(key);
  const bold = weight >= 600;
  for (const g of GLYPH_FALLBACKS) {
    if (g.family === SCRIPTS_FAMILY && g.weight >= 600 !== bold) continue;
    addFontFace(family, weight, g.url, () => injected.delete(key), g.unicodeRange);
  }
}

function injectFamily(family: string, weight: number, uploaded: UploadedFont[]): void {
  const key = `${family}:${weight}`;
  if (injected.has(key)) return;
  injected.add(key);
  injectGlyphFallbacks(family, weight);
  if (family === FALLBACK_FAMILY) {
    addFontFace(family, weight, fallbackUrl(weight));
    return;
  }
  const up = uploadedUrl(family, uploaded);
  if (up) {
    // Uploaded bytes are auth-gated, so a bare `url()` can't fetch them; pull the
    // bytes (with the bearer) and hand the ArrayBuffer straight to FontFace.
    void fetchFontBytes(up).then((buf) => {
      if (buf) addFontFace(family, weight, buf);
      else injected.delete(key);
    });
  } else {
    // Mirror the Satori rule so preview == export: a missing family shows the
    // bundled fallback, registered under the brand's own name so the card's
    // font-family resolves the same way in both. (A legacy value naming a system
    // font, e.g. "Georgia", is therefore stood in for on this page too.) Anything
    // else (a transient failure, or a real family lacking this weight) clears the
    // dedup key so a later render retries, as before.
    addFontFace(family, weight, ttfUrl(family, weight), () => {
      void familyIsMissing(family, uploaded).then(async (missing) => {
        if (!missing) {
          injected.delete(key);
          return;
        }
        const buf = await fetchFontBytes(fallbackUrl(weight), false);
        if (buf) addFontFace(family, weight, buf);
        else injected.delete(key);
      });
    });
  }
}

/** Inject @font-face for the DOM live preview so it renders in the workspace
 *  fonts (not the app's), matching the Satori export. Idempotent per family. */
export function injectBrandFontFaces(fonts: BrandFonts, uploaded: UploadedFont[] = []): void {
  if (typeof document === "undefined") return;
  for (const req of requiredFonts(fonts, uploaded)) injectFamily(req.family, req.weight, uploaded);
}

/** Inject a single 400-weight @font-face for `family` so a Settings preview can
 *  render it — the same TTF the card uses (uploaded bytes or the CDN). */
export function injectFontFace(family: string, uploaded: UploadedFont[] = []): void {
  if (typeof document === "undefined" || !family.trim()) return;
  injectFamily(family, 400, uploaded);
}
