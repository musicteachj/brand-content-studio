// Deterministic text-fit for the card headline. Satori does not auto-shrink
// overflowing text and the card is a fixed 1080×1350 box with `overflow: hidden`,
// so a long edited headline (or copy written for one layout, swapped into a
// tighter one — Phase 1.5) would clip. This estimates the rendered height
// geometrically and steps the font size down until it fits.
//
// It is a pure function of the text + box, so the live DOM preview, the locked
// Satori preview, and the PNG export all compute the SAME size → preview ==
// export by construction (ARCHITECTURE §5). It is intentionally an estimate, not
// a DOM measurement: no layout thrash, no font-load race, fully testable.

export interface FitSpec {
  text: string;
  /** Starting (largest) font size in px — the design size for the layout. */
  max: number;
  /** Smallest font size we'll shrink to before accepting clipping. */
  min: number;
  /** Line-height multiplier used by the element. */
  lineHeight: number;
  /** Inner width available to the text, px. */
  boxWidth: number;
  /** Height the text may occupy before it crowds the rest of the card, px. */
  boxHeight: number;
  /** Mean glyph advance as a fraction of font size (heading fonts ≈ 0.52). */
  avgAdvance?: number;
}

/** The largest size in [min, max] at which `text` is estimated to fit within
 *  `boxWidth × boxHeight`. Shrinks in 2px steps for stable, snap-free results. */
export function fitTextSize(spec: FitSpec): number {
  const { text, max, min, lineHeight, boxWidth, boxHeight, avgAdvance = 0.52 } = spec;
  const trimmed = text.trim();
  if (!trimmed) return max;

  const longestWord = trimmed.split(/\s+/).reduce((n, w) => Math.max(n, w.length), 0);

  for (let size = max; size > min; size -= 2) {
    const charWidth = size * avgAdvance;
    const charsPerLine = Math.max(1, Math.floor(boxWidth / charWidth));
    // A single word can't break, so it forces a minimum line count too.
    if (longestWord > charsPerLine) continue; // too wide at this size — keep shrinking
    const lines = Math.ceil(trimmed.length / charsPerLine);
    const height = lines * lineHeight * size;
    if (height <= boxHeight) return size;
  }
  return min;
}
