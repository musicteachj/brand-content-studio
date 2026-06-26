# Phase 4 — Brand setup & learning (slice plan)

> **Status: PR-A (4a + 4b) built + verified on `feat/4-workspace`.** Server gate (ruff + mypy +
> 49 pytest) and client gate (tsc + eslint + prettier + build + 37 vitest) green; live acceptance
> run passed (create/switch a 2nd brand surviving reload; edit palette/fonts/voice/accent + logo
> upload; demo blocked). Pending PR-A: Tier-2 review gate → commit → push → PR into `dev`.
> **PR-B (4c — vision brand-learning) not started.** Phase-boundary `dev → main` + tag `v0.6.0`
> stays deferred per [bcs-phase-state] (releases cut closer to deploy).
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

## PR-B design (4c — pending)

- **`services/brand_extract_service.py`** — Pillow dominant-color palette + Claude **multimodal**
  (forced strict tool-use, reuse the generation tool-use pattern) → a structured
  `{colors[], voice_summary, fonts?}` **proposal**. Add `Pillow` to `requirements.txt`.
- **`POST /workspaces/{id}/brand/extract`** (multipart) → returns the proposal (never auto-applied);
  reuse the upload validation/storage helpers.
- **Example-card exemplar steering** — uploaded past brand cards (images); vision extracts copy
  patterns + visual direction stored on the workspace and injected as extra brand context. **Honesty
  guard (DECISIONS #23 / R2): approximate via our Satori archetypes — never pixel-clone.** Decide
  storage shape (`brand_profile.exemplars` vs. a small collection) at the PR-B contract step.
- **Client** — an "Extract from upload" affordance in the brand editor that shows the proposal as a
  **diff to review + apply** (never silent overwrite), then saves via the existing PATCH.

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
