// The curated brand-font set. Heading/Body pick from serif+sans; Mono from mono.
// Every serif/sans family here MUST have a bundled TTF server-side for PDF parity
// (see server/tests/test_brand_fonts.py CURATED_PDF_FAMILIES — keep in sync).
export type FontCategory = "serif" | "sans" | "mono";

export interface FontOption {
  family: string;
  category: FontCategory;
  /** The weights fontsource ships for it, so the card never requests one that
   *  can only 404 (DM Serif Display is 400 only). */
  weights: readonly number[];
}

const ALL = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const;

// Weights from fontsource's metadata API (api.fontsource.org/v1/fonts/<id>), 2026-10.
export const FONT_OPTIONS: FontOption[] = [
  { family: "DM Serif Display", category: "serif", weights: [400] },
  { family: "Playfair Display", category: "serif", weights: [400, 500, 600, 700, 800, 900] },
  { family: "Fraunces", category: "serif", weights: ALL },
  { family: "Spectral", category: "serif", weights: [200, 300, 400, 500, 600, 700, 800] },
  { family: "Lora", category: "serif", weights: [400, 500, 600, 700] },
  { family: "Inter", category: "sans", weights: ALL },
  { family: "Work Sans", category: "sans", weights: ALL },
  { family: "Libre Franklin", category: "sans", weights: ALL },
  { family: "Archivo", category: "sans", weights: ALL },
  { family: "JetBrains Mono", category: "mono", weights: [100, 200, 300, 400, 500, 600, 700, 800] },
  { family: "IBM Plex Mono", category: "mono", weights: [100, 200, 300, 400, 500, 600, 700] },
];

/** The weights a curated family ships (any casing, like the CDN slug), or null
 *  for a family outside the catalog. */
export function catalogWeights(family: string): readonly number[] | null {
  const canonical = findCatalogFamily(family);
  return FONT_OPTIONS.find((o) => o.family === canonical)?.weights ?? null;
}

export type FontRole = "heading" | "body" | "mono";

export interface FontSelectOption {
  value: string;
  label: string;
}

/** The Select options for a role: a "Default" empty option, the role-appropriate
 *  families, the workspace's uploaded families (usable in any role), and — if the
 *  stored value isn't in either set — a preserved "<name> (current)" option so a
 *  Select never silently drops saved data. */
export function optionsForRole(
  role: FontRole,
  current: string | null,
  uploaded: string[] = [],
): FontSelectOption[] {
  const cats: FontCategory[] = role === "mono" ? ["mono"] : ["serif", "sans"];
  const families = FONT_OPTIONS.filter((o) => cats.includes(o.category)).map((o) => o.family);
  const opts: FontSelectOption[] = [
    { value: "", label: "Default" },
    ...families.map((f) => ({ value: f, label: f })),
    ...uploaded.map((f) => ({ value: f, label: `${f} (uploaded)` })),
  ];
  if (current && !families.includes(current) && !uploaded.includes(current)) {
    opts.push({ value: current, label: `${current} (current)` });
  }
  return opts;
}

/** Canonical catalog family for a (case-insensitive) name, or null if unknown.
 *  With a `role`, only that role's categories count (mono for mono, else serif/sans). */
export function findCatalogFamily(name: string | null | undefined, role?: FontRole): string | null {
  if (!name) return null;
  const lower = name.trim().toLowerCase();
  const cats: FontCategory[] | null = role
    ? role === "mono"
      ? ["mono"]
      : ["serif", "sans"]
    : null;
  return (
    FONT_OPTIONS.find(
      (o) => o.family.toLowerCase() === lower && (!cats || cats.includes(o.category)),
    )?.family ?? null
  );
}
