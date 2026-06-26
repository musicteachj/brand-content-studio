# Phase 1.5 — Customization (slice plan)

> **Status: built + verified on `feat/1.5-customization`** — all four slices + History hydration landed;
> server gate (ruff + mypy + 31 pytest) and client gate (tsc + eslint + prettier + build + 20 vitest) green;
> review gate Tier 2 done (`/code-review` high: 1 fixed — CardThumb accent parity; `/security-review` full:
> clean); **live acceptance run passed** (inline edit + re-export with no `/generate`, image/layout swap
> keeps copy, edits persist). Pending: commit → push → PR into `dev`; phase boundary `dev → main` + tag
> `v0.3.0` (Tier 3, incl. user-run `/code-review ultra`).
>
> Working plan for `v0.3.0` / branch `feat/1.5-customization` (off `dev`). Follows
> [PLAN.md](./PLAN.md) §"Phase 1.5", [WORKFLOW.md](./WORKFLOW.md) (vertical slices, contract-first,
> backend-first), [DESIGN.md](./DESIGN.md), and [DECISIONS.md](./DECISIONS.md). Resolves the two
> open questions in DECISIONS (workspace brand-color UI tint; the accent toggle).

## Goal

Make a generated card **editable after the fact, entirely client-side** — change the copy, swap the
layout, swap the image, and choose the accent — and re-export **without ever re-calling Claude**.
The model wrote the card once; customization is a design loop, not a generation loop.

**Acceptance (PLAN.md):** edit a headline in-preview and re-export with the client making **no
`/generate` request**; swap image and template without losing copy; changes persist on save.
pytest: `PATCH` updates `output.fields`; re-export makes no `/generate` call.

## Resolved decisions (confirmed with the owner)

1. **Workspace brand-color UI tint** → a **Settings toggle, default ON**. When on and a workspace is
   active, override Folio `--accent` with the workspace primary brand color for *cosmetic* UI tint
   only (active nav, selected states). Never touches semantic tokens (success/warning/destructive)
   — DESIGN §7. Resolves the DECISIONS open question.
2. **Inline editing UX** → edit **directly on the card** (the preview is the hero; no side panel),
   via editable DOM fields overlaid on the locked Satori `<img>`. Edits are **ephemeral in local
   state** until an **explicit Save** (with Discard); Save PATCHes once and re-renders Satori.
3. **Edits update the existing generation** (PATCH), not a fork.
4. **Accent toggle is per-card** → which brand-palette color is *this card's* accent, stored on
   `output.accent_hex`, re-rendered client-side. Distinct from the workspace UI tint (#1).
5. **Layout swap** → free swap, render immediately, **auto-scale text to fit** the fixed 1080×1350
   bounds (same fit logic covers long edited headlines). No blocking overflow warnings.
6. **Settings page (quiet)** → theme toggle, the brand-tint toggle (#1), and a read-only workspace
   identity block (name, color swatches, fonts). Nothing else.

## What already exists (reuse, do NOT rebuild)

- `PATCH /api/workspaces/{id}/generations/{gid}` + `GenerationUpdate{template_id, fields, image}` —
  ownership- and card-type-guarded, merges into `output`. **Not** `is_demo`-guarded (demo edits its
  own generations). Adding `accent_hex` to the contract is the only backend change this phase.
- `useCardExport` (`renderCardSvg`/`svgToPng`/`downloadCardPng`) + History re-export — re-export with
  no model call already works; History re-exports from persisted `output`.
- The shared card element `cards/cardElement.tsx` (`buildCardElement` + `cardColors` already reads
  `brand.accent_hex`) → live DOM preview == locked Satori == PNG export by construction.
- Image swap surviving a regenerate (`useCardGeneration.ts`); `ImagePickerPanel`.

## Contract change (one)

`CardOutput.accent_hex: str | null` and `GenerationUpdate.accent_hex: str | null` (server), mirrored
in the TS `CardOutput` type. Validated as one of the workspace brand-palette hexes (server-side
guard). `cardColors()` already prefers an explicit accent override; thread a per-card `accentHex`
through `CardElementProps` so it wins over `brand.accent_hex`.

## Slice sequence (each: contract → backend+pytest → client → polish → self-review)

All four slices ship on the one `feat/1.5-customization` branch (they share `CardPreview` /
`cardElement` / the PATCH contract); commit per slice.

1. **Layout swap** — re-render the same `output.fields` in a different archetype, PATCH `template_id`,
   **no `/generate`**. Adds the fit-to-bounds text scaler (reused by slice 3). *Acceptance:* swap
   template on a finished/re-opened card, copy preserved, persists, no generate call.
2. **Accent toggle (per-card) + workspace UI tint** — `accent_hex` contract + a brand-palette swatch
   picker on the card; the Settings-driven `--accent` tint applied app-wide when active. *Acceptance:*
   pick an accent → card re-renders → persists; tint toggle flips Folio↔brand accent, semantic tokens
   unchanged.
3. **Inline text editing** — editable fields on the locked preview, dirty-state Save/Discard, PATCH
   `output.fields`, re-render Satori, re-export with **no `/generate`** (the headline acceptance).
4. **Settings page** — replace the `ComingSoon` stub at `/settings` with theme + tint toggle +
   read-only workspace identity.

## Tests

- pytest: `PATCH` updates `output.fields`; `PATCH` updates `template_id`; `PATCH accent_hex` rejects a
  non-palette hex; existing ownership/card-type guards still hold.
- vitest: the fit-text scaler shrinks an over-long headline within bounds; editing a field then
  re-exporting issues **no** `/generate` fetch (assert on the fetch mock); per-card `accentHex` wins
  over `brand.accent_hex` in `cardColors`.

## Review gate

PATCH touches generations persistence → **Tier 2**: `/code-review` high + `/security-review` full
before the first push. No commit/push without explicit per-action approval. Fold any UI improvements
back into DESIGN.md (DECISIONS #18); update CHANGELOG `0.3.0` and DECISIONS (close the two open
questions) at phase end.
