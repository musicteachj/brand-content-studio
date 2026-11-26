// Workspace brand-color UI tint (DESIGN §4). When enabled and a workspace is
// active, the Folio `--accent` token is overridden with the workspace's primary
// brand color so active nav + selected states wear the brand. This is COSMETIC
// ONLY — it never touches semantic tokens (success/warning/destructive), per
// DESIGN §7. Tokens are HSL triplets ("H S% L%") consumed as hsl(var(--token)).

interface Hsl {
  h: number;
  s: number;
  l: number;
}

/** Expand shorthand (#abc -> abc → aabbcc) and validate. Returns the 6 hex digits
 *  (no #), or null if the string isn't a valid hex color. */
function normalizeHex(hex: string): string | null {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((x) => x + x)
          .join("")
      : h;
  return /^[0-9a-fA-F]{6}$/.test(full) ? full : null;
}

function hexToHsl(hex: string): Hsl | null {
  const full = normalizeHex(hex);
  if (!full) return null;
  const r = parseInt(full.slice(0, 2), 16) / 255;
  const g = parseInt(full.slice(2, 4), 16) / 255;
  const b = parseInt(full.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let hue = 0;
  if (d !== 0) {
    if (max === r) hue = ((g - b) / d) % 6;
    else if (max === g) hue = (b - r) / d + 2;
    else hue = (r - g) / d + 4;
    hue *= 60;
    if (hue < 0) hue += 360;
  }
  const l = (max + min) / 2;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  return { h: hue, s: s * 100, l: l * 100 };
}

function triplet({ h, s, l }: Hsl): string {
  return `${Math.round(h)} ${Math.round(s)}% ${Math.round(l)}%`;
}

// The two candidate foregrounds for the accent fill, as (triplet, 6-hex) pairs so
// we can measure real contrast against the accent, not guess from HSL lightness.
const DARK_INK = { triplet: "214 12% 12%", hex: "1a1d21" };
const WHITE = { triplet: "0 0% 100%", hex: "ffffff" };

/** WCAG relative luminance (sRGB, linearized). Input is 6 hex digits (no #).
 *  0 = black, 1 = white. */
function relativeLuminance(full: string): number {
  const chan = (i: number) => {
    const c = parseInt(full.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(0) + 0.7152 * chan(2) + 0.0722 * chan(4);
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// The accent-derived tokens we override together so the tint stays internally
// consistent (no leftover magenta in the strong/ring variants).
const ACCENT_TOKENS = ["--accent", "--accent-strong", "--accent-foreground", "--ring"] as const;

/** Override (or, when `hex` is null/invalid, clear) the accent token group on the
 *  document root. Clearing restores the stylesheet's Folio magenta. */
export function applyAccentTint(hex: string | null): void {
  const root = document.documentElement;
  const hsl = hex ? hexToHsl(hex) : null;
  if (!hsl) {
    for (const t of ACCENT_TOKENS) root.style.removeProperty(t);
    return;
  }
  root.style.setProperty("--accent", triplet(hsl));
  // A slightly darker strong variant for hover/press depth.
  root.style.setProperty("--accent-strong", triplet({ ...hsl, l: Math.max(0, hsl.l - 8) }));
  // The ring is drawn against a near-white surface (light is the primary theme).
  // A pale brand color (e.g. cream #F4F1E9) would vanish, so clamp its lightness
  // to a band that always shows a visible outline.
  root.style.setProperty("--ring", triplet({ ...hsl, l: Math.min(55, Math.max(25, hsl.l)) }));
  // Readable foreground on the accent fill: whichever of dark-ink / white has the
  // higher WCAG contrast against the accent. HSL lightness is NOT perceptual
  // luminance — e.g. pure yellow #FFFF00 is L=50 but needs black text (white =
  // 1.07:1), which the old `hsl.l > 60` test got exactly wrong.
  const accentHex = normalizeHex(hex!)!; // non-null: hexToHsl above already parsed it
  const fg =
    contrastRatio(accentHex, WHITE.hex) >= contrastRatio(accentHex, DARK_INK.hex)
      ? WHITE.triplet
      : DARK_INK.triplet;
  root.style.setProperty("--accent-foreground", fg);
}
