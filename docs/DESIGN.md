# Brand Content Studio — Design System ("Folio")

> **Reference, not gospel.** This system and the [`mocks/`](./mocks/) are the design *starting point*, not a pixel-exact spec. Frontend work uses the Claude design skills (`frontend-design` / `impeccable` / `ui-ux-pro-max`); when a skill yields a clearly better UI/UX, adopt it and update this doc. Folio's tokens and identity are the baseline to evolve from — see [`DECISIONS.md`](./DECISIONS.md) #18.

> **Chosen identity: "Folio."** A distinct, app-specific look — deliberately NOT the developer's
> portfolio brand, the Smart Resume Builder's "Editorial Ink," or any client's brand system.
> Every project gets its own identity. Folio treats brand content creation as a craft: **Plus Jakarta Sans**
> for headings and UI, **DM Mono** for labels and eyebrow text, a cool studio-white canvas (not warm
> paper — that's Editorial Ink's territory) with a single reserved magenta accent (`#C2185B`).
> Polished, creative, calm. External craft references (Linear, Framer, Notion, Craft)
> inform *polish* only — not the look.
>
> Philosophy: **creative restraint** — the card preview is always the hero, the UI is always the frame.
> Light-first for color accuracy. Token-driven (no raw hex in components). Hairline borders + crisp
> cool shadows. Purposeful motion. When in doubt, remove rather than add.

---

## 0. North Star — "a creative tool that gets out of the way"

The app exists to produce beautiful branded content. Every UI decision should serve that goal.

- **The card preview is the hero** — on the Generate page, the designed card output is the focal point.
  All surrounding UI should recede. Never let chrome compete with the content being created inside it.
- **Neutral host, not a brand** — this app hosts any company's brand assets. Its own visual identity
  must be warm and distinctive but never so opinionated that it clashes with workspace brand colors.
  The app chrome disappears; the client's brand takes center stage.
- **Light-first for creative judgment** — users are making visual decisions: choosing photos, reviewing
  copy, evaluating how colors read. Light mode is correct for color accuracy. Dark mode is a user
  preference, not the primary experience.
- **AI surfaces stay quiet** — generation loading states and retrieval indicators must feel like precise,
  trustworthy tooling. No gradient glows, no animated shimmer beyond a tasteful skeleton state.
- **Highest-risk surfaces** for drifting generic-or-gimmicky: the **landing page** (mocked, not built yet) and the **Generate page
  card preview panel** — hold both firmly in the creative-restraint lane and review against this North
  Star before shipping.

---

## 1. Design tokens (CSS variables → consumed by Tailwind)

Define as HSL/HEX CSS vars on `:root` and `.dark`; map into Tailwind through the `@theme` block in `client/src/index.css` (`--color-*: hsl(var(--token))`; Tailwind 4 has no `tailwind.config.ts`).
**No component may hardcode a hex.**

"Folio" tokens (light = primary experience; dark = warm-charcoal, not pure black). Verify all
foreground/background pairs for contrast independently per theme.

| Token (Tailwind name) | CSS var | Light | Dark |
|---|---|---|---|
| `background` (studio white) | `--background` | `#F8F9FA` | `#18191B` |
| `surface` (card) | `--surface` / `--card` | `#FFFFFF` | `#222426` |
| `surface-variant` | `--surface-variant` | `#F1F3F5` | `#2C2F32` |
| `foreground` (primary text) | `--foreground` | `#1A1D21` | `#F0F2F4` |
| `muted-foreground` (secondary) | `--muted-foreground` | `#5F666D` (darkened from `#6C737A` for AA on `surface-variant`) | `#9AA0A8` |
| `accent` (CTA/active — RESERVED) | `--accent` / `--primary` | `#C2185B` | `#E91E8C` |
| `accent-strong` (hover/press) | `--accent-strong` | `#9E1248` | `#C2185B` |
| `accent-foreground` | `--accent-foreground` | `#FFFFFF` | `#1A0510` |
| `border` (hairline) | `--border` | `#E4E7EA` | `#363B40` |
| `ring` (focus) | `--ring` | `#C2185B` (solid accent, drawn as a 2px ring) | `#E91E8C` |
| `success` | `--success` | `#15803D` | `#4ADE80` |
| `warning` | `--warning` | `#B45309` | `#F59E0B` |
| `destructive` | `--destructive` | `#B42318` | `#F87171` |
| `destructive-foreground` | `--destructive-foreground` | `#FFFFFF` | `#311313` (dark ink on the light-red fill) |
| `preview-bg` (card canvas surround) | `--preview-bg` | `#E8EAED` | `#111314` |

> **Accent — Magenta (`#C2185B`):** Confirmed during the UI design phase. The accent token set in the
> code is `--accent`, `--accent-strong`, `--accent-foreground`, and `--ring` (values in the table), plus
> `--shadow-accent` (`0 8px 24px rgb(194 24 91 / .22)`, §3). There are no separate soft, ring, or
> shadow accent variables. With **Brand color tint** on (the default), all four color tokens are
> overridden at runtime from the active workspace's primary brand color (§4).
> Used only for the primary CTA per view, active nav state, focused field ring, and selected state.
> Never decoratively. Distinguish from `success` (outcomes) by reserving accent for *actions*.

> **preview-bg:** The card preview panel gets a slightly darker warm surround to frame the card as a
> canvas. This is the only surface darker than `background` in light mode — used exclusively for the
> Generate page preview area.

---

## 2. Typography

- **Display / headings:** `Plus Jakarta Sans` (variable; weights 400/500/600/700), letter-spacing
  `-0.01em` to `-0.015em`. Used for page headings, section titles, and marketing display. Warmer and
  more distinctive than Inter; chosen specifically for a creative productivity context.
- **Body / UI / form labels / buttons:** `Plus Jakarta Sans` (400/500), body line-height 1.6.
  Same family as headings — unified feel, differentiated by weight and size rather than font switch.
- **Eyebrow labels / data / mono accent:** `DM Mono` (400/500), uppercase, `0.12em` tracking, muted
  color. Used for category labels, workspace metadata, asset counts, and technical indicators.
  Gives the app a precise, crafted edge without overusing mono.
- **Card preview content:** Uses the *workspace's own brand typography* as defined in the workspace
  profile. App fonts must never leak into the card preview output — the card is the client's artifact,
  not the app's UI.
- `font-display: swap`; preload only Plus Jakarta Sans + DM Mono.
- **Type scale (rem):** 0.75 / 0.875 / 1 / 1.125 / 1.25 / 1.5 / 1.875 / 2.25 / 3
  (+ landing hero `clamp(2.75rem, 6vw, 4.5rem)`, reserved for the landing page, which isn't built yet).
  Two extra small sizes exist for mono labels: `text-2xs` 0.625rem (10px, the default `eyebrow`) and
  `text-3xs` 0.5625rem (9px, tiny badges such as history type tags and template labels). Page-header
  eyebrows use 11px.

---

## 3. Spacing / radius / shadow / z-index

- **Spacing:** 8px base — 8/16/24/32/48/64/80/96. Section rhythm tiers 24/32/48/64.
- **Radius:**
  - `sm` 6px — chips, tags, input fields
  - `md` 8px — buttons, dropdowns
  - `lg` 12px — cards, side panels, asset list items
  - `xl` 16px — modals, overlays, the card preview frame
  - `full` — avatars, pills, toggle switches
- **Shadows (bespoke crisp cool, not warm editorial):**
  - `--shadow-light` `0 1px 2px rgb(26 29 33 / .04), 0 2px 6px rgb(26 29 33 / .05)`
  - `--shadow-medium` `0 4px 12px rgb(26 29 33 / .08)`
  - `--shadow-heavy` `0 12px 32px rgb(26 29 33 / .12)`
  - `--shadow-accent` `0 8px 24px rgba(194,24,91,.22)` (hover on primary CTA only)
  - `--shadow-preview` `0 8px 32px rgb(26 29 33 / .18)` (card preview canvas elevation)
- Cards/surfaces use **1px border + light shadow**, never heavy elevation.
- **z-index scale:** 0 / 10 (sticky header) / 20 (dropdown) / 40 (side drawer) / 60 (image picker panel)
  / 100 (modal) / 1000 (toast, reserved: the app has no toasts; feedback is inline, e.g. "Copied" on the
  button that copied).

---

## 4. Component conventions

- **Buttons:** primary = solid `accent` + `accent-foreground`, `radius-md`, hover lifts via
  `--shadow-accent`, press scale `0.98`; secondary = `surface` + `border`; ghost = transparent;
  destructive = `destructive`. One primary per view. Disabled = opacity 0.5 + `cursor-not-allowed`.
  Async states = spinner replacing icon + disabled, never just a frozen button.
- **Inputs:** outlined (`border`), `radius-sm`, visible label above (never placeholder-only), helper text
  below, error text below in `destructive` + `role="alert"`; focus = 2px `ring`. Validate on blur,
  focus first invalid on submit.
- **Side navigation:** Fixed left sidebar, collapsible to icon-only; starts collapsed below `lg` (desktop-first, DECISIONS #39). Active item = `accent` left border
  + `surface-variant` background. Icon + label when expanded, icon-only with tooltip when collapsed.
  Never top nav inside the app — landing page only.
- **Cards (content history grid):** `surface` + 1px `border` + `shadow-light`; hover `translateY(-2px)`
  + `shadow-medium`; a mono type tag (`POST + CARD`, `CARD`, `TEXT`, `DOCUMENT`) and date, the brief,
  then the artifact (card thumbnail at reduced scale, text snippet, or document header) and a source
  count. Actions sit inline under each card, by type: Download + Caption (LinkedIn post), Download
  (card), Copy (text post), or the format download row (document). Clicking the card opens the
  **History detail dialog** (below), which holds Customize and the confirmed Delete. Uploaded images
  are left out of thumbnails (they're auth-gated); Unsplash photos show.
- **Asset list items:** `surface-variant` rows with 1px `border` separator; ingestion status indicator
  (processing / ready / error) as a small pill — never color alone, always paired with icon and label.
- **Template picker:** A 3-column grid of card layout thumbnails (Photo-led, Statement, Quote), drawn in
  the workspace's colors, each with a mono label underneath. Selected state = 2px `accent` border +
  `shadow-light`. Hover = `shadow-light`. In Image card mode nothing is preselected (the user must
  choose); LinkedIn post mode defaults to Photo-led.
- **Card generation flow — guided in place, not a wizard** (Phase 1b, evolved from the build): the card
  has implicit steps (template → brief → generate → image → export), so the Generate page makes them
  legible *without* a multi-screen stepper, which would fight the North Star (the preview is the hero and
  cards are generated in quick succession). The left controls panel carries **numbered step markers** in
  the mono eyebrow style: a small numbered circle followed by `TEMPLATE` or `BRIEF`. A completed step's
  circle fills with `accent` and shows a check, the current step's circle is outlined in `accent`, and an
  upcoming step is a muted `surface-variant` circle. An optional **Preset** select sits above step 1
  when the workspace has saved card presets. The two **finishing actions live on the card
  itself** (right column, under the preview): *Add an image* (photo-led; image selection is parallel and
  available while copy still streams) and *Export*. Once the card is ready but image-less, the *Add an
  image* button is outlined in `accent` to mark it as the suggested next step. Wizards remain reserved for
  genuine one-time setup (Workspace Setup), not for the in-tool creative loop.
- **Unsplash image picker:** Panel slides in from the right over the Generate page. Search input at top,
  masonry grid of results below. Selected image = `accent` ring. Attribution line ("Photo by X on
  Unsplash") rendered automatically — non-negotiable, required by Unsplash license. The search starts
  from the model's suggested keywords. An **Upload** button takes your own JPG, PNG, or WebP; owners
  then get **Save to brand images** ("Saved ✓" once done). The workspace's **Brand images** sit in
  their own row above the search results. Empty, searching (skeleton tiles), no-results, and
  can't-reach-Unsplash states are all inline in the panel.
- **Card preview panel:** Sits on `--preview-bg` surround. The card itself is `radius-xl` + `shadow-preview`.
  Streaming copy appears token by token directly in the preview — no separate text output area.
  The finishing actions (Add/Change image · Edit text · Export) sit in one wrapping row under the card.
- **Card customization (Phase 1.5) — quiet, beneath the hero.** Post-generation, a recessed *Customize*
  panel (`surface` + hairline) under the preview offers **Layout** (the `TemplatePicker` thumbnails,
  now also a no-regenerate swap) and **Accent** (a row of round brand-palette swatches; selected =
  2px `foreground` ring + a luminance-aware check — never accent-on-accent). A `warning`-mono "Unsaved"
  marker plus a **Discard / Save changes** pair appear only when the draft is dirty. **Inline text
  editing happens on the card itself:** an *Edit text* toggle swaps the locked Satori image for the
  live DOM card with `contentEditable` fields (dashed `currentColor` affordance + placeholder via
  `.card-edit-field`, sized in 1080px card space so it reads at preview scale); a single *Done editing*
  action returns to the locked preview. Edits are ephemeral until Save (which `PATCH`es); export and the
  History re-export never call the model. The same editor hydrates a **re-opened History card** (a
  *Customize* action on the detail dialog), so layout/accent/copy/image edits work there too.
- **LinkedIn-post mode (Phase 3) — the first *objective*, a paired preview.** A Generate mode
  (first in the toggle) that yields a post **caption + matching card** from one brief. The preview
  pairs the **card** (the reused `CardPreview` — the visual hero) beside an **editable caption**
  panel (`PostCaptionPanel`): the caption streams in live (`aria-live`, the same token motion),
  then becomes a paste-ready textarea with a Copy action; the card resolves once distilled. Image
  pick (parallel) + Export PNG live on the card; Copy lives on the caption. Both are workspace-brand
  (the card never uses Folio chrome, DESIGN §7). History shows a post_pack as a card thumbnail +
  caption snippet, with Customize / Download PNG / Copy caption on the detail dialog.
- **Document mode (Phase 2) — the document is the hero, like the card.** A third Generate mode
  (Text / Card / **Document**) reusing the brief box + retrieval debug panel. The card-preview hero is
  swapped for a **`DocumentPreview`**: the draft streams as prose into a quiet "Drafting" panel
  (`aria-live`, the same token-by-token motion as text/card — no extra animation), then resolves into the
  branded one-pager **"paper"** (`DocumentPage`) on the `--preview-bg` surround. The paper renders in the
  **workspace's own colors + fonts** (title/headings = brand primary, eyebrow/bullets = brand accent,
  body = document ink on white — never Folio chrome, DESIGN §7); the on-screen page mirrors the generated
  `.docx`/PDF by construction (one server-side `DocumentModel` drives both). A **format download row**
  (`.docx` · PDF) sits under the page; each button pulls the pre-rendered file through the auth-gated
  download route with **no model call**. In History, a document generation shows a compact thumbnail
  (header-only) + the same multi-format download row on the grid card and the detail dialog.
  - **Archetypes render in their own shape (`DocumentArtifact`):** the **one-pager** is "paper"
    (`DocumentPage`, → `.docx`/PDF); the **short-deck** is a stack of branded 16:9 **slide cards**
    (`DeckPreview` — title slide → content slides → closing, → `.pptx`). Both render from the one
    `DocumentModel` in workspace colors/fonts, mirroring the generated file; `compact` (title-slide /
    header-only) drives History thumbnails. The download row shows whichever formats the archetype built.
- **Settings page — appearance + brand management.** Sectioned, single-column, `max-w-2xl`:
  a **Theme** segmented control (Light / Dark / System), a **Brand color tint** pill switch (the
  optional workspace `--accent` override, default on; cosmetic only), a **Workspaces** section, and a
  **Brand identity** card.
  - **Workspaces section (Phase 4a):** a bordered list of the owner's workspaces — active badge,
    inline **rename**, and **delete** (confirm Dialog, keeps ≥1) — plus a **New workspace** button
    routing to `/setup`. Anchored `#workspaces` (the switcher's "Manage workspaces" deep-links here).
  - **Brand identity card (Phase 4b):** read-only by default (palette swatches + accent marker +
    fonts + voice + logo) with an **Edit** affordance that reveals the editable form (palette CRUD with
    a native color-picker swatch, accent-from-palette select, font inputs, voice textarea, logo
    upload/preview/remove). Logo saves immediately; field edits save on **Save changes**. Disabled for
    the demo user. Resolved in [DECISIONS.md](./DECISIONS.md) #23.
  - **Learn from an image (Phase 4c):** a dashed-border "Extract from image" affordance at the top of
    the edit form. Uploading a logo/guideline image returns a **proposed** palette/voice/fonts shown in
    a review panel (swatches + voice + fonts); **Apply to form** fills the fields for review, then the
    normal **Save changes** persists — the proposal is never auto-applied. Allowed for the demo user
    (generative preview, not a mutation).
  - **Example cards (Phase 4c):** a separate "Example cards" Settings section — a list of uploaded
    past brand cards (4:5 thumbnails + the extracted style note + remove) and an "Add example card"
    upload that shows an extracting state. Persists immediately (like the logo); capped at 5 ("N of 5")
    and demo-disabled. The notes steer generated copy via a trusted prompt block (DECISIONS #23).
  - **Brand images:** a grid of the workspace's own images (capped at 24, "N of 24"), each with an
    inline-editable caption and a trash button revealed on hover (confirmed). "Add image" uploads;
    the image picker's Brand images row and its "Save to brand images" both feed this list.
  - **Brand fonts:** upload `.ttf` files (capped at 8) under a family name typed first ("Give the font
    a name first" if empty). Each row previews the font in itself. Uploaded families join the font
    selects in Brand identity and render on cards and exported PDFs.
  - **Card presets:** a create form (name, the `TemplatePicker`, and an accent row of "Default" plus
    the palette swatches) and a list of saved presets showing name, accent dot, and layout tag
    (capped at 8; at the cap the form is replaced by a limit notice). Presets appear in the Image card
    **Preset** select.
  - Every remove or delete in Settings goes through a **confirm dialog** (below).
- **Templates page (Phase 5) — bring your own branded file.** A nav entry (`LayoutTemplate`):
  upload/list/delete `.docx`/`.pptx` templates (rows show format + placeholder count), then **Use** one
  → a fill view with a field per `{{placeholder}}` (labelled by tag name) plus an optional **"Draft
  with AI"** (a brief populates the fields, still editable) or **"Fill from a document"** (upload a
  .docx, .pptx, .pdf, .txt, or .md under 10 MB and the fields are filled from it) → **Download**. A
  template with no placeholders says so and downloads unchanged. The output keeps the
  template's *own* styling — we only swap text — so it's never re-skinned with Folio or `brand_profile`
  (DECISIONS #24). Renders download immediately (not stored). Upload/delete are demo-disabled via the
  shared `DemoNotice`; empty state prompts a first upload. The one fidelity caveat (a `.pptx` tag with
  mixed inline formatting collapsing to its paragraph's first-run style) is noted to the user.
- **Workspace switcher (Phase 4a) — TopBar dropdown.** Replaces the static workspace name in the top
  bar: the `Workspace` eyebrow + active name become a dropdown trigger (chevron) listing the owner's
  workspaces (active check), then **New workspace** and **Manage workspaces**. Switching persists the
  active id (survives reload); create/manage are demo-aware. Built on a Folio `dropdown-menu` wrapper
  over Radix (`z-dropdown`, surface/border/`shadow-heavy`, matching the Dialog).
- **Generation loading state:** Text streams in place with a thin blinking caret (text post, LinkedIn
  caption, document draft under a "Drafting" eyebrow). The card shows a quiet drafting card
  ("Writing…") until its copy is final; then, while the exact export image renders, the export button
  briefly reads "Preparing…" over the live preview. While generating, the Generate button becomes
  **Stop**. List pages (History, Assets) and the image picker use pulsing skeleton tiles or rows. No
  full-page spinners.
- **Ingestion progress indicator:** A small status pill on each asset row: **Processing** (spinner, the
  list polls until it settles) → **Ready**, or **Error** with the reason in `destructive` text under the
  filename and a **Retry** action. Never blocks the rest of the UI. Long lists page in 30 at a time
  behind a **Load more** button (History pages in 24).
- **Workspace brand color application:** A **Settings toggle (default on)** overrides the `--accent`
  token with the active workspace's primary brand color for subtle UI tinting on active nav items and
  selected states (applied via `useAppearance` → `applyAccentTint`, which also derives `--accent-strong`
  / `--ring` / `--accent-foreground`). Cosmetic only — never affects semantic tokens
  (success/warning/destructive). Resolved in [DECISIONS.md](./DECISIONS.md) #20.
- **Retrieved context panel:** a quiet bordered panel under the Generate preview (and inside the History
  detail dialog) showing which brand chunks fed the generation. Header: "Retrieved context" plus a mono
  "N chunks · Nms" count. Each row: source filename, a mono kind tag (`VOICE`, `POSTS`, `PILLARS`...),
  a page number for PDFs, then either a mono similarity score with a thin score bar or a **Pinned** marker
  (voice and pillar chunks, always included and listed first), and a short excerpt. Footer: embedding model and `k`. Before the
  first generation it shows one muted line explaining what will appear.
- **History detail dialog:** opened by clicking a History card. Header: the brief, then a mono
  "type · model · date" line. Body: the artifact (card, post text, or document) and the Retrieved
  context panel. Footer actions by type: Customize, Download PNG, and Copy caption (cards and LinkedIn
  posts), Copy text (text posts), the format download row (documents), and **Delete** (owners only,
  confirmed).
- **Confirm dialog:** every delete or remove asks first. A centered `surface` dialog with a title naming
  the item (`Delete “competitors.md”?`), one line on the consequence, then **Cancel** and a
  `destructive` action labeled with the verb ("Delete asset", "Remove image"). If the action fails, the
  dialog stays open with the error inline.
- **Demo notice:** in the demo session, read-only pages (Assets, Templates, Settings) open with a
  `surface-variant` banner, a lock icon, and one muted paragraph explaining what's read-only. Elsewhere,
  demo-blocked controls are simply disabled (native tooltip "Disabled in the demo"). The sidebar shows a
  "Demo session" eyebrow under the user name.
- **Sign in page:** a two-column split at `lg` and up. Left: the Folio mark, a mono eyebrow, the headline
  "Your brand's voice. Retrieved, not invented.", a short paragraph, and a sample Verdure card. Right:
  "Sign in" with **Explore as demo** as the primary button, an "or sign in" divider, Email and Password
  fields, and a secondary **Sign in** button. Errors appear in an inline alert above the fields. Below
  `lg` the left panel is hidden. There is no public sign-up.
- **Folio mark:** a 32px rounded `foreground` tile with a `background`-colored "F" (Plus Jakarta Sans
  600), beside "Folio" with a `STUDIO` eyebrow under it. The collapsed sidebar shows only the tile.
  Because it uses `foreground` / `background`, it inverts in dark mode. The favicon
  (`client/public/favicon.svg`) is the same F on a magenta `#C2185B` tile.

---

## 5. Motion

- Durations 150–300ms micro, ≤400ms transitions; exit ~60–70% of enter. Easing: ease-out enter,
  ease-in exit.
- Animate `transform` / `opacity` only. Never width/height/top/left. 1–2 animated elements per view.
- Stagger content history grid cards 20–40ms on load.
- Entrance `fadeInUp` `cubic-bezier(0.16, 1, 0.3, 1)`.
- Card preview copy streaming: characters appear naturally via JS text insertion, no additional animation.
  The streaming itself is the motion — do not add fade or slide on top of it.
- Image picker panel: slides in from right `translateX(100%) → 0`, 250ms ease-out.
- **All motion gated behind `prefers-reduced-motion`** (reduce/disable).

---

## 6. Accessibility (non-negotiable)

- Contrast ≥4.5:1 body / ≥3:1 large + UI glyphs; verify light *and* dark independently.
  Magenta `#C2185B` on `#FFFFFF` = 4.6:1 ✓. Verify `#C2185B` on `#F8F9FA` before shipping.
- Visible 2px focus ring on every interactive element; tab order matches visual order.
- Icon-only buttons get `aria-label`; SVG icons only (Lucide React) — **no emoji as icons**.
- Form labels via `<label for>`; errors `role="alert"` + `aria-live`; required fields marked.
- Color never the sole signal — ingestion status, template selection, and validation states all pair
  icon and/or text with color.
- Sequential heading hierarchy; skip-to-content link; respect Dynamic Type / zoom (no `maximum-scale`).
- Card preview panel: when streaming copy, `aria-live="polite"` on the text container so screen readers
  receive updates without being overwhelmed.
- Unsplash attribution must remain visible and readable at all zoom levels — do not hide in a tooltip.

---

## 7. Anti-patterns / forbidden

- ❌ Hardcoded hex in components — tokens only.
- ❌ App fonts (Plus Jakarta Sans / DM Mono) bleeding into the card preview — the card uses the
  workspace's own brand typography. App fonts are app chrome only.
- ❌ The portfolio's fonts (JetBrains Mono / IBM Plex) or Smart Resume Builder's fonts (Fraunces) —
  this app is intentionally its own identity.
- ❌ Pure black `#000` or harsh pure-white surfaces — use warm canvas/ink tokens.
- ❌ Dark-first design — light mode is the primary experience. Dark mode is a user preference.
- ❌ Heavy Material elevation — hairline borders + soft warm shadows only.
- ❌ Accent color used decoratively, in backgrounds, or in body text — reserved for actions only.
- ❌ Workspace brand colors bleeding into semantic tokens (success/warning/destructive).
- ❌ Full-page loading spinners — skeleton states on affected components only.
- ❌ Placeholder-as-label; errors only at top of form; removing focus rings.
- ❌ Animating layout properties / motion with no meaning / ignoring reduced-motion.
- ❌ Unsplash images used without attribution — license requires visible credit.
- ❌ Card preview competing with app chrome — the preview is always the focal point on the Generate
  page. If the UI is drawing more attention than the card, something is wrong.
- ❌ Trendy gimmicks: glassmorphism, neon, chromatic/iridescent effects, gradient "AI sparkle,"
  animated gradient borders, frosted glass panels.
- ❌ Emoji as icons anywhere in the app UI.
