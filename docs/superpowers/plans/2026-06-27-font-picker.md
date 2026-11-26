# Curated Font Picker + PDF Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the free-text brand-font inputs with a curated picker over a vetted OFL set, and bundle that set's TTFs so a chosen font renders the same on a card and embeds in an exported PDF.

**Architecture:** Client-mostly. A pure `fontCatalog` module drives `<Select>`s in the brand editor (stored shape unchanged — still `fonts.{heading,body,mono}` family strings); the card pipeline is untouched (still loads via the fontsource CDN). Server: bundle each curated serif/sans family's regular TTF into the existing `brand_fonts_dir` so `resolve_font_file` embeds them in PDFs, guarded by a parity test.

**Tech Stack:** React + react-hook-form + Vitest (client); FastAPI + pytest (server). Client cmds from `client/` via `./node_modules/.bin/<tool>`; server cmds from `server/` (`.venv/bin/...`).

**Spec:** `docs/superpowers/specs/2026-06-27-font-picker-design.md`

**Branch:** `feat/font-picker` (off `dev`, already created; spec already committed).

**Curated set (OFL):** serif — DM Serif Display, Playfair Display, Fraunces, Spectral, Lora; sans — Inter, Work Sans, Libre Franklin, Archivo; mono — JetBrains Mono, IBM Plex Mono. (DM Serif Display + Spectral already bundled; mono is metadata-only — not bundled.)

**File structure:**
- Create `client/src/styles/fontCatalog.ts` — the curated list + pure helpers (one responsibility: what fonts exist + per-role options).
- Create `client/src/styles/fontCatalog.test.ts`.
- Modify `client/src/styles/brandFonts.ts` — add `injectFontFace` for the editor preview.
- Modify `client/src/features/settings/BrandIdentityEditor.tsx` — `<Input>` → `<Select>` + preview.
- Modify `client/src/features/settings/brandIdentity.ts` + `brandIdentity.test.ts` — snap extract proposals to the catalog.
- Create `server/tests/test_brand_fonts.py` — parity guard.
- Add 7 TTFs + `LICENSE.md` under `server/app/assets/fonts/`.
- Docs: `docs/DECISIONS.md`, `CHANGELOG.md`.

---

### Task 1: Font catalog + pure helpers

**Files:**
- Create: `client/src/styles/fontCatalog.ts`
- Test: `client/src/styles/fontCatalog.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/styles/fontCatalog.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { FONT_OPTIONS, findCatalogFamily, optionsForRole } from "./fontCatalog";

describe("fontCatalog", () => {
  it("has serif, sans, and mono families", () => {
    const cats = new Set(FONT_OPTIONS.map((o) => o.category));
    expect(cats).toEqual(new Set(["serif", "sans", "mono"]));
  });

  it("offers serif+sans for heading/body and mono for mono", () => {
    const heading = optionsForRole("heading", null).map((o) => o.value);
    expect(heading).toContain("DM Serif Display"); // serif
    expect(heading).toContain("Inter"); // sans
    expect(heading).not.toContain("JetBrains Mono"); // mono excluded
    expect(optionsForRole("mono", null).map((o) => o.value)).toContain("JetBrains Mono");
  });

  it("puts a Default empty option first", () => {
    expect(optionsForRole("body", null)[0]).toEqual({ value: "", label: "Default" });
  });

  it("preserves a stored non-catalog value as a (current) option", () => {
    const opts = optionsForRole("heading", "Comic Sans");
    expect(opts.at(-1)).toEqual({ value: "Comic Sans", label: "Comic Sans (current)" });
  });

  it("does not duplicate a catalog value into (current)", () => {
    expect(optionsForRole("heading", "Inter").filter((o) => o.value === "Inter")).toHaveLength(1);
  });

  it("matches a family name case-insensitively", () => {
    expect(findCatalogFamily("inter")).toBe("Inter");
    expect(findCatalogFamily("Unknown Face")).toBeNull();
    expect(findCatalogFamily(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/styles/fontCatalog.test.ts`
Expected: FAIL — `fontCatalog` doesn't exist.

- [ ] **Step 3: Create `client/src/styles/fontCatalog.ts`**

```ts
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
 *  families, and — if the stored value isn't in the catalog — a preserved
 *  "<name> (current)" option so a Select never silently drops saved data. */
export function optionsForRole(role: FontRole, current: string | null): FontSelectOption[] {
  const cats: FontCategory[] = role === "mono" ? ["mono"] : ["serif", "sans"];
  const families = FONT_OPTIONS.filter((o) => cats.includes(o.category)).map((o) => o.family);
  const opts: FontSelectOption[] = [
    { value: "", label: "Default" },
    ...families.map((f) => ({ value: f, label: f })),
  ];
  if (current && !families.includes(current)) {
    opts.push({ value: current, label: `${current} (current)` });
  }
  return opts;
}

/** Canonical catalog family for a (case-insensitive) name, or null if unknown. */
export function findCatalogFamily(name: string | null | undefined): string | null {
  if (!name) return null;
  const lower = name.trim().toLowerCase();
  return FONT_OPTIONS.find((o) => o.family.toLowerCase() === lower)?.family ?? null;
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/styles/fontCatalog.test.ts`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add client/src/styles/fontCatalog.ts client/src/styles/fontCatalog.test.ts
git commit -m "feat(fonts): curated font catalog + per-role option helpers"
```

---

### Task 2: Picker in the brand editor + live preview + proposal snap

**Files:**
- Modify: `client/src/styles/brandFonts.ts`
- Modify: `client/src/features/settings/BrandIdentityEditor.tsx`
- Modify: `client/src/features/settings/brandIdentity.ts`
- Test: `client/src/features/settings/brandIdentity.test.ts`

- [ ] **Step 1: Write the failing test** — extend `client/src/features/settings/brandIdentity.test.ts`. Add at the end of the file (inside the top-level `describe`, or as a new `describe`):

```ts
import { findCatalogFamily } from "@/styles/fontCatalog";

describe("proposalToForm font snapping", () => {
  it("snaps a proposed font name to the catalog casing", () => {
    const form = proposalToForm({
      colors: [],
      voice_summary: null,
      fonts: { heading: "inter", body: "playfair display", mono: null },
    });
    expect(form.fonts.heading).toBe("Inter");
    expect(form.fonts.body).toBe("Playfair Display");
  });

  it("keeps an unknown proposed font as-is (preserved as a current option)", () => {
    const form = proposalToForm({
      colors: [],
      voice_summary: null,
      fonts: { heading: "Some Custom Face", body: null, mono: null },
    });
    expect(form.fonts.heading).toBe("Some Custom Face");
    expect(findCatalogFamily(form.fonts.heading)).toBeNull();
  });
});
```

(`proposalToForm` is already imported at the top of this test file. Adjust the `proposalToForm({...})` argument shape if `BrandExtract` differs — it is `{ colors, voice_summary, fonts: { heading, body, mono } }`.)

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/features/settings/brandIdentity.test.ts`
Expected: FAIL — `heading` comes back `"inter"`, not `"Inter"` (no snapping yet).

- [ ] **Step 3: Snap proposals in `client/src/features/settings/brandIdentity.ts`.** Add the import at the top (with the other imports):

```ts
import { findCatalogFamily } from "@/styles/fontCatalog";
```

Then in `proposalToForm`, replace the `fonts` block:

```ts
    fonts: {
      heading: p.fonts.heading ?? "",
      body: p.fonts.body ?? "",
      mono: p.fonts.mono ?? "",
    },
```

with:

```ts
    fonts: {
      heading: findCatalogFamily(p.fonts.heading) ?? p.fonts.heading ?? "",
      body: findCatalogFamily(p.fonts.body) ?? p.fonts.body ?? "",
      mono: findCatalogFamily(p.fonts.mono) ?? p.fonts.mono ?? "",
    },
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/features/settings/brandIdentity.test.ts`
Expected: PASS.

- [ ] **Step 5: Add `injectFontFace` to `client/src/styles/brandFonts.ts`** (after `injectBrandFontFaces`, reusing the module-private `injected` set + `ttfUrl`):

```ts
/** Inject a single 400-weight @font-face for `family` so a Settings preview can
 *  render it — the same fontsource TTF the card uses. Idempotent per family. */
export function injectFontFace(family: string): void {
  if (typeof document === "undefined" || !family.trim()) return;
  const key = `${family}:400`;
  if (injected.has(key)) return;
  injected.add(key);
  const style = document.createElement("style");
  style.dataset.brandFont = key;
  style.textContent = `@font-face{font-family:"${family}";font-style:normal;font-weight:400;font-display:swap;src:url("${ttfUrl(
    family,
    400,
  )}") format("truetype");}`;
  document.head.appendChild(style);
}
```

- [ ] **Step 6: Swap the inputs for selects in `client/src/features/settings/BrandIdentityEditor.tsx`.**

(a) Ensure imports — add `useEffect` to the React import if absent, add `Select`, the catalog helpers, and `injectFontFace`:

```ts
import { useEffect } from "react";
import { Select } from "@/components/ui/select";
import { optionsForRole } from "@/styles/fontCatalog";
import { injectFontFace } from "@/styles/brandFonts";
```

(b) Replace the entire `{/* Fonts */}` block (the `grid ... sm:grid-cols-3` div with the three `<Input>`s) with:

```tsx
      {/* Fonts */}
      <div className="grid gap-3 border-t border-border pt-5 sm:grid-cols-3">
        <div className="flex flex-col">
          <Label htmlFor="font-heading">Heading font</Label>
          <Select id="font-heading" {...register("fonts.heading")}>
            {optionsForRole("heading", watch("fonts.heading")).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.heading")} />
        </div>
        <div className="flex flex-col">
          <Label htmlFor="font-body">Body font</Label>
          <Select id="font-body" {...register("fonts.body")}>
            {optionsForRole("body", watch("fonts.body")).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.body")} />
        </div>
        <div className="flex flex-col">
          <Label htmlFor="font-mono">Mono font</Label>
          <Select id="font-mono" {...register("fonts.mono")}>
            {optionsForRole("mono", watch("fonts.mono")).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.mono")} />
        </div>
      </div>
```

(c) Add the `FontPreview` component at the bottom of the file (module scope, after the editor component):

```tsx
function FontPreview({ family }: { family: string | null | undefined }) {
  useEffect(() => {
    if (family) injectFontFace(family);
  }, [family]);
  if (!family) return null;
  return (
    <p
      className="mt-1.5 truncate text-sm text-muted-foreground"
      style={{ fontFamily: `"${family}", serif` }}
    >
      The quick brown fox
    </p>
  );
}
```

- [ ] **Step 7: Typecheck + lint + format**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}"`
Expected: clean. (If `Input` is now unused in the editor, remove it from the import to satisfy eslint.)

- [ ] **Step 8: Commit**

```bash
git add client/src/styles/brandFonts.ts client/src/features/settings/BrandIdentityEditor.tsx client/src/features/settings/brandIdentity.ts client/src/features/settings/brandIdentity.test.ts
git commit -m "feat(fonts): curated picker + live preview in the brand editor"
```

---

### Task 3: Server parity-guard test (RED)

**Files:**
- Create: `server/tests/test_brand_fonts.py`

- [ ] **Step 1: Write the parity test**

Create `server/tests/test_brand_fonts.py`:

```python
"""Parity guard: every curated serif/sans family the picker offers must have a
bundled TTF, so a font chosen for a card also embeds in an exported PDF."""
from app.services.brand_fonts import resolve_font_file

# Mirror the serif/sans entries of client/src/styles/fontCatalog.ts (keep in sync).
CURATED_PDF_FAMILIES = [
    "DM Serif Display",
    "Playfair Display",
    "Fraunces",
    "Spectral",
    "Lora",
    "Inter",
    "Work Sans",
    "Libre Franklin",
    "Archivo",
]


def test_curated_families_have_bundled_ttf():
    missing = [fam for fam in CURATED_PDF_FAMILIES if resolve_font_file(fam) is None]
    assert missing == [], f"missing bundled TTFs for: {missing}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_brand_fonts.py -q`
Expected: FAIL — only DM Serif Display + Spectral are bundled; the other 7 are missing.

- [ ] **Step 3: Commit the test**

```bash
git add server/tests/test_brand_fonts.py
git commit -m "test(fonts): PDF parity guard — curated families must have bundled TTFs"
```

---

### Task 4: Bundle the curated TTFs (GREEN)

**Files:**
- Add: `server/app/assets/fonts/{playfair-display,fraunces,lora,inter,work-sans,libre-franklin,archivo}.ttf`
- Create: `server/app/assets/fonts/LICENSE.md`

- [ ] **Step 1: Fetch the 7 new regular-weight TTFs** (verified reachable; slugs match `font_slug`):

```bash
cd server/app/assets/fonts && for slug in playfair-display fraunces lora inter work-sans libre-franklin archivo; do
  curl -fsSL -o "$slug.ttf" "https://cdn.jsdelivr.net/fontsource/fonts/$slug@latest/latin-400-normal.ttf"
done
```

- [ ] **Step 2: Verify they are valid TrueType files**

Run: `cd server/app/assets/fonts && for f in playfair-display fraunces lora inter work-sans libre-franklin archivo; do printf "%-18s %s %s\n" "$f" "$(stat -f%z "$f.ttf")" "$(xxd -p -l 4 "$f.ttf")"; done`
Expected: each non-trivial size with magic `00010000` (TrueType).

- [ ] **Step 3: Create `server/app/assets/fonts/LICENSE.md`**

```markdown
# Bundled brand fonts

These TTFs are bundled so the PDF renderer can embed a workspace's brand font
locally (no runtime fetch — see `app/services/brand_fonts.py`). All are licensed
under the SIL Open Font License (OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/<slug>@latest/latin-400-normal.ttf`), which
mirrors Google Fonts.

- DM Serif Display — OFL
- Playfair Display — OFL
- Fraunces — OFL
- Spectral — OFL
- Lora — OFL
- Inter — OFL
- Work Sans — OFL
- Libre Franklin — OFL
- Archivo — OFL

The curated set is defined in `client/src/styles/fontCatalog.ts` (serif/sans
families must have a TTF here — guarded by `server/tests/test_brand_fonts.py`).
Mono families (JetBrains Mono, IBM Plex Mono) are metadata-only and not bundled.
```

- [ ] **Step 4: Run the parity test to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_brand_fonts.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/assets/fonts/
git commit -m "feat(fonts): bundle curated serif/sans TTFs for PDF embedding + LICENSE"
```

---

### Task 5: Gates

- [ ] **Step 1: Server gate**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all pass (117).

- [ ] **Step 2: Client gate**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --check "src/**/*.{ts,tsx}" && ./node_modules/.bin/vitest run && ./node_modules/.bin/vite build`
Expected: all green (vitest +~8: 6 catalog + 2 proposal-snap).

- [ ] **Step 3: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(fonts): gates green"
```

---

### Task 6: Docs

**Files:** `docs/DECISIONS.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add a row after the `#28` row:

```
| 29 | Curated font picker + PDF parity | Brand fonts are chosen from a **curated set** of ~11 OFL families (serif/sans for heading+body, mono for mono) via `<Select>`s in the editor (replacing free-text inputs) — not validated free text that silently fell back to Georgia. The set's serif/sans **TTFs are bundled** in `app/assets/fonts/` so a chosen font both renders on the card (via the fontsource CDN, unchanged) and **embeds in exported PDFs** (`resolve_font_file`) — closing the card↔PDF asymmetry; a parity test (`test_brand_fonts.py`) fails if a picker family lacks a bundled TTF. Stored shape unchanged (`fonts.{heading,body,mono}` name strings); a legacy/custom value is preserved as a "(current)" option (renders on cards, won't embed in PDF). Mono is metadata-only (no render path → not bundled). **Deferred:** user font-file upload; self-hosting card fonts to drop the CDN. | free-text fonts were typo-prone + silently fell back, and a card font wasn't embedded in PDFs unless its TTF happened to be bundled | A small vetted set covers brand needs cheaply, makes selection previewable + reliable, and — because the picker defines exactly which fonts exist — lets us bundle precisely those TTFs for guaranteed card↔PDF parity with no new endpoints. |
```

- [ ] **Step 2: CHANGELOG** — under `## [Unreleased]`, add at the top:

```markdown
### Added — Curated font picker + PDF parity

Brand fonts are now chosen from a curated set of ~11 OFL families (with a live preview) instead of free-text inputs that silently fell back to Georgia on a typo. The set's serif/sans TTFs are bundled server-side, so a chosen font renders on the card **and** embeds in an exported PDF — closing the previous card↔PDF asymmetry. A legacy/custom font value is preserved as a "(current)" option; mono stays metadata-only. Brand auto-extract now snaps proposed font names to the catalog. Client-only picker + bundled fonts; no new endpoints, storage shape unchanged. See [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#29). Tests: vitest (+8) — the catalog helpers + proposal snapping; pytest (+1) — the PDF parity guard.
```

- [ ] **Step 3: Commit**

```bash
git add docs/DECISIONS.md CHANGELOG.md
git commit -m "docs(fonts): curated picker + parity — DECISIONS #29 + CHANGELOG"
```

---

### Task 7: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 5) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: TTFs are committed static assets from a known OFL source; the `@font-face`/preview interpolates a family name into CSS — confirm it can't break out of the `url()`/family string; `resolve_font_file` keeps its path-traversal guard.)
- [ ] **Step 4: Live verify (owner):** Settings → Brand identity → Heading/Body/Mono are dropdowns with previews; pick e.g. Heading = Playfair Display, Body = Lora → Save → generate a card (renders in those fonts) → export a **document PDF** and confirm the body text is the real Lora (embedded), not a generic serif. A workspace with a legacy font name shows it as "(current)".
- [ ] **Step 5: Owner commit/push approval**, then push `feat/font-picker` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** curated set (Task 1 `FONT_OPTIONS`) ✓; picker replaces free text, role-filtered, Default option, stored shape unchanged (Task 2) ✓; live preview via `injectFontFace` (Task 2) ✓; legacy/custom value preserved as "(current)" (Task 1 `optionsForRole`, tested) ✓; brand-extract snap (Task 2, tested) ✓; bundle serif/sans TTFs + LICENSE (Task 4) ✓; mono metadata-only / not bundled (Task 1 catalog has mono but Task 3 `CURATED_PDF_FAMILIES` excludes it) ✓; parity-guard test (Task 3) ✓; cards unchanged / CDN kept (no card-pipeline task — by design) ✓; docs (Task 6) ✓.

**Placeholder scan:** none — every code step is concrete.

**Type consistency:** `optionsForRole(role, current)` / `findCatalogFamily(name)` (Task 1) match their uses in the editor + `proposalToForm` (Task 2). `injectFontFace(family)` (Task 2 Step 5) matches its `FontPreview` use (Step 6c). `CURATED_PDF_FAMILIES` (Task 3) lists exactly the serif+sans `FONT_OPTIONS` families (Task 1) — the families bundled in Task 4. `resolve_font_file` + `font_slug` already exist in `brand_fonts.py`; slugs of the listed families equal the fetched filenames (Task 4).
```
