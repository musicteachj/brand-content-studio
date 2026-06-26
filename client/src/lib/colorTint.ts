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

function hexToHsl(hex: string): Hsl | null {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((x) => x + x)
          .join("")
      : h;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
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
  root.style.setProperty("--ring", triplet(hsl));
  // Readable foreground on the accent fill, chosen by luminance.
  root.style.setProperty("--accent-foreground", hsl.l > 60 ? "214 12% 12%" : "0 0% 100%");
}
