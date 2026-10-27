# Phase 4 — Brand setup & learning (slice plan)

> **Update (2026-10-27):** merged into `dev` as PRs #7, #8, and #9. The `dev → main` release and its tag haven't happened yet; releases were deferred to one release closer to deploy. The status note below is kept as written at the time.
>
> **Status: PR-A (4a + 4b) + PR-B (4c auto-extract) merged to `dev` (PRs #7, #8). PR-C (4c
> exemplar steering) built on `feat/4c-exemplars`.** PR-C gates green (ruff + mypy + 72 pytest;
> tsc + eslint + prettier + build + 42 vitest). Pending PR-C: live verify (real vision call) →
> Tier-2 review gate → owner commit/push approval → PR into `dev`. **4c was split: PR-B =
> auto-extract; PR-C = exemplar steering.** Phase-boundary `dev → main` + tag `v0.6.0` stays
> deferred per [bcs-phase-state] (releases cut closer to deploy).
>
> The second phase of the pre-deployment enhancements plan. Follows the approved roadmap
> (LinkedIn-post objective → **brand setup & learning** → on-brand templates → robustness),
> [DECISIONS.md](./DECISIONS.md) (#23), and [WORKFLOW.md](./WORKFLOW.md).

## Goal

Make the app genuinely **multi-brand and editable in-app**: switch between workspaces, manage them,
and edit a workspace's whole brand identity (palette, fonts, voice, accent, logo) from the UI —
then (PR-B) **learn** a brand from real inputs (a brand-guideline/logo, example cards).

**Acceptance:** create/switch to a 2nd brand, edit its profile in-app, upload a logo, generate
on-brand in each workspace, and confirm History/retrieval never cross. The demo user can switch but
cannot mutate.

## Why this is reuse-heavy

A read-only audit found the backend already multi-tenant: workspace **CRUD**, per-owner slug
uniqueness, `get_workspace_or_404` ownership, `require_not_demo` guards, and a `PATCH /workspaces/{id}`
that already merges `brand_profile`. The gap was **client-only** (single auto-selected workspace, a
read-only brand card) plus the **modeled-but-unimplemented** logo upload.

## PR split

- **PR-A = 4a + 4b** (`feat/4-workspace` → `dev`) — switcher/manage + brand editor + logo. *Built.*
- **PR-B = 4c** (new `feat/*` off `dev` after PR-A) — vision brand-learning. *Pending.*

---

## PR-A design (built)

### 4a — Workspace switcher + management (client only)
- **TopBar dropdown** (`components/layout/WorkspaceSwitcher.tsx` over a new Folio
  `components/ui/dropdown-menu.tsx` Radix wrapper): lists workspaces (active check), switches via
  `stores/workspace.setActive`, routes to **New workspace** (`/setup`) + **Manage workspaces**
  (`/settings#workspaces`). New-workspace disabled for demo.
- **Settings → Workspaces** (`features/settings/WorkspacesSection.tsx`): list + inline **rename** +
  **delete** (confirm Dialog, keeps ≥1), demo-disabled.
- **Resolver**: `useActiveWorkspace` already lets a persisted `activeId` win over the first-load
  fallback (switch survives reload); only stale/empty ids fall back to the first. Clarified + tested.
- **API**: `useUpdateWorkspace(id)` (PATCH), `useDeleteWorkspace()` — reuse existing CRUD, no new
  server routes.

### 4b — Brand editor + logo (server + client)
- **Server logo route** — `POST` / `DELETE /workspaces/{id}/logo` in `routes/workspaces.py`,
  mirroring the `routes/images.py` upload defenses (allow-listed type, 8 MB cap, server-derived key
  via `build_image_key`); persists through a **targeted** `workspace_service.set_workspace_logo` /
  `clear_workspace_logo` (`$set`/`$unset` on `brand_profile.logo`, never a whole-profile replace);
  served by the existing image route. `resolve_image_content_type` made public for reuse. Demo-guarded.
- **Brand field edits** — no new server code; `PATCH /workspaces/{id}` already merges (replaces)
  `brand_profile`. The client sends the **full** profile on Save.
- **Client editor** (`features/settings/BrandIdentityEditor.tsx` + pure `brandIdentity.ts`) —
  read-only by default; **Edit** reveals a `react-hook-form` + `zod` form: palette CRUD (name + hex +
  color-picker + role), fonts, voice, accent-from-palette (validated), logo upload/preview/remove
  (immediate). Disabled for demo.

## Reuse (do NOT rebuild)
`routes/workspaces.py` CRUD, `PATCH /workspaces/{id}`, `get_workspace_or_404`, `require_not_demo`,
the `routes/images.py` upload/serve pattern + `storage_service` key builders, `useActiveWorkspace` /
`stores/workspace`, `fetchImageDataUrl`, the Folio `Button`/`Input`/`Label`/`Select`/`Textarea` +
Radix `Dialog`/`DropdownMenu`. Genuinely new: the dropdown wrapper, the switcher, the Workspaces
section, the brand editor, and the two logo routes.

---

## PR-B design (4c auto-extract — built)

Decisions (owner-confirmed): **split 4c** (B = auto-extract, C = exemplar steering); **image-only**
input for v1 (no PDF-raster dep); **demo allowed** for extract (apply stays demo-blocked).

- **`services/brand_extract_service.py`** — `extract_palette` (Pillow MEDIANCUT quantize → exact
  dominant hexes, deterministic/unit-testable) + `BrandExtractService.propose` (forced strict Claude
  **vision** tool-use: the image + detected hexes → `{colors, voice_summary, fonts}`), shaped by
  `build_extract_response` (blanks → null; falls back to the detected palette). `Pillow` declared in
  `requirements.txt`. Tool/prompt in `prompts/brand_extract.py` (`BRAND_EXTRACT_TOOL`).
- **`POST /workspaces/{id}/brand/extract`** (multipart, image-only) — same allow-list/size defenses
  as the logo route; `get_workspace_or_404` ownership, **no `require_not_demo`** (generative, not a
  mutation); returns `BrandExtractResponse` and **never touches the DB**.
- **Client** — `useExtractBrand` (no invalidation); the brand editor's "Extract from image"
  affordance shows the proposal as a **review panel** → **Apply to form** (`proposalToForm` →
  replaces palette/fonts/voice, clears accent) → user reviews → **Save** (the existing PATCH). Never
  silently applied.

## PR-C design (exemplar steering — built)

Decisions (owner-confirmed): **pre-extract to text** on upload (not per-generation multimodal);
**store on `brand_profile.exemplars`** (cap 5); inject into the **generate trio** (text/card/post).
Full design: `docs/superpowers/specs/2026-06-26-exemplar-steering-design.md`; plan:
`docs/superpowers/plans/2026-06-26-exemplar-steering.md`.

- Upload a past card → one forced strict Claude **vision** tool-use call (`EXEMPLAR_NOTE_TOOL` in
  `prompts/brand_extract.py`, `propose_exemplar_note` in `brand_extract_service`) extracts a short
  `style_note`; stored on `brand_profile.exemplars` via targeted `add_workspace_exemplar`
  (`$push`)/`remove_workspace_exemplar` (`$pull` + delete bytes). `POST`/`DELETE
  /workspaces/{id}/exemplars` — same upload defenses as the logo, **409 at cap 5**, demo-blocked,
  **extract-before-store** (a vision failure persists nothing).
- At generation, `build_exemplar_guidance(notes)` joins the notes into a trusted block that
  `text_post.build_system` / `image_card.build_copy_system` append after the voice summary; the three
  generate routes pass it (post_pack's caption uses `text_post.build_system`).
- Client: `useAddExemplar`/`useRemoveExemplar` + a Settings **Example cards** section
  (`ExemplarsSection`) — thumbnails + notes + add/remove, disabled at cap / for demo.
- **Honesty guard (DECISIONS #23 / R2): approximate via our Satori archetypes — never pixel-clone.**

---

## Verification

Stack: `docker-compose up` (mongo :27017, chroma :8001) + server `:8000` (`env -u
ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m uvicorn app.main:app --port 8000`) +
`npm run dev` (Vite :5173).

**Multi-use checklist:** create a 2nd workspace via the switcher (survives reload) → edit its
colors/fonts/voice + upload a logo → generate in each (History/retrieval never cross) → rename +
delete from Settings → as demo: switching works, every mutation is disabled/403. (PR-B) upload a
guideline/logo → review the proposed palette/voice → apply → generate reflects it.

Per-PR gate: server `ruff` + `mypy` + `pytest`; client `tsc` + `eslint` + `prettier` + `build` +
`vitest`; then `/code-review` + `/security-review`, owner commit/push approval, PR into `dev`.
