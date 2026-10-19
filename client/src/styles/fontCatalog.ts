// The curated brand-font set. Heading/Body pick from serif+sans; Mono from mono.
// Every serif/sans family here MUST have a bundled TTF server-side for PDF parity
// (see server/tests/test_brand_fonts.py CURATED_PDF_FAMILIES — keep in sync).
export type FontCategory = "serif" | "sans" | "mono";

export interface FontOption {
  family: string;
  category: FontCategory;
}

export const FONT_OPTIONS: FontOption[] = [
  { family: "DM Serif Display", category: "serif" },
  { family: "Playfair Display", category: "serif" },
  { family: "Fraunces", category: "serif" },
  { family: "Spectral", category: "serif" },
  { family: "Lora", category: "serif" },
  { family: "Inter", category: "sans" },
  { family: "Work Sans", category: "sans" },
  { family: "Libre Franklin", category: "sans" },
  { family: "Archivo", category: "sans" },
  { family: "JetBrains Mono", category: "mono" },
  { family: "IBM Plex Mono", category: "mono" },
];

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
