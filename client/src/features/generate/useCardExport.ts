// Card rendering + export. Satori turns the shared card element (cardElement.tsx)
// into an SVG; @resvg/resvg-wasm rasterizes that SVG to an exact 1080×1350 PNG.
// The locked on-screen preview shows the SAME SVG, so preview == export by
// construction (ARCHITECTURE §5, DECISIONS #11). satori + resvg are dynamically
// imported so they stay out of the initial bundle.
import { useEffect, useState } from "react";
import { fetchImageDataUrl } from "@/api/images";
import {
  buildCardElement,
  CARD_H,
  CARD_W,
  type CardElementProps,
} from "@/features/generate/cards/cardElement";
import { loadBrandFontBuffers } from "@/styles/brandFonts";
import type { BrandProfile, CardOutput } from "@/types";

let resvgReady: Promise<void> | null = null;

async function ensureResvg(): Promise<void> {
  if (!resvgReady) {
    const attempt = (async () => {
      const { initWasm } = await import("@resvg/resvg-wasm");
      const wasmUrl = (await import("@resvg/resvg-wasm/index_bg.wasm?url")).default;
      await initWasm(fetch(wasmUrl));
    })();
    // Don't memoize a rejected init — a transient wasm-load failure must not
    // permanently break every later export. Clear the cache on failure so the
    // next call retries.
    attempt.catch(() => {
      resvgReady = null;
    });
    resvgReady = attempt;
  }
  return resvgReady;
}

/** Render the card element to an SVG string via Satori (workspace fonts as
 *  buffers). Throws a friendly error if no brand font could be loaded — Satori
 *  needs at least one. */
export async function renderCardSvg(props: CardElementProps): Promise<string> {
  const { default: satori } = await import("satori");
  const fonts = await loadBrandFontBuffers(props.brand.fonts);
  if (fonts.length === 0) {
    throw new Error("Could not load the workspace brand fonts. Check your connection and retry.");
  }
  return satori(buildCardElement(props), { width: CARD_W, height: CARD_H, fonts });
}

/** Rasterize an SVG to an exact 1080×1350 PNG blob. */
export async function svgToPng(svg: string): Promise<Blob> {
  await ensureResvg();
  const { Resvg } = await import("@resvg/resvg-wasm");
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: CARD_W } });
  const png = resvg.render().asPng();
  return new Blob([png as BlobPart], { type: "image/png" });
}

export function cardPngName(headline: string): string {
  const slug = (headline || "card")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 48)
    .replace(/^-+|-+$/g, "");
  return `${slug || "card"}-1080x1350.png`;
}

/** Re-export a persisted card to PNG from its stored `output` — no model call
 *  (Phase 1.5 re-export, pulled forward into History). Fetches the image bytes
 *  fresh (Unsplash URL or our auth-gated upload URL), re-renders via Satori, and
 *  downloads. */
export async function downloadCardPng(output: CardOutput, brand: BrandProfile): Promise<void> {
  const imageSrc = output.image?.url ? await fetchImageDataUrl(output.image.url) : null;
  const svg = await renderCardSvg({
    template: output.template_id,
    fields: output.fields,
    brand,
    imageSrc,
    attribution: output.image?.attribution ?? null,
    accentHex: output.accent_hex,
  });
  const png = await svgToPng(svg);
  downloadBlob(png, cardPngName(output.fields.headline));
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Produce the locked-preview SVG once `enabled` (the copy is finalized). Returns
 *  the SVG string, plus loading/error so the preview can fall back to the live DOM
 *  card while it renders or if Satori fails. */
export function useCardSvg(enabled: boolean, props: CardElementProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const key = JSON.stringify({
    t: props.template,
    f: props.fields,
    a: props.accentHex ?? null,
    img: props.imageSrc ? props.imageSrc.length : null,
    attr: props.attribution,
    fonts: props.brand.fonts,
    colors: props.brand.colors,
  });

  useEffect(() => {
    if (!enabled) {
      setSvg(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    renderCardSvg(props)
      .then((out) => {
        if (!cancelled) setSvg(out);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `key` captures every input that changes the render; props is read inside.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, key]);

  return { svg, error, loading };
}

export function svgToDataUrl(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
