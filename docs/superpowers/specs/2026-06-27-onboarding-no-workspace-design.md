# First-run / Zero-Workspace Onboarding Gate — Design

**Goal:** When an authenticated owner has **no workspaces**, guide them to create one instead of dropping them onto dead-end action pages. Close the UX gap exposed by real (non-demo) owner accounts, which start with zero workspaces. (The demo user always owns the seeded Verdure workspace, so this path was never reachable before.)

**Non-goal:** No server change. Every workspace-scoped route already enforces a real, owned workspace via `get_workspace_or_404` (404 otherwise), so this is purely a client-side guidance gap — not a security or data-integrity hole.

## Background

- `useActiveWorkspace()` already computes `hasNone = !isLoading && !isError && workspaces.length === 0`, and it's unit-tested — but **no component consumes it**.
- `App.tsx` has no onboarding guard: all seven routes render unconditionally once authenticated.
- With zero workspaces (`workspaceId === null`): Generate silently no-ops (`generate()` early-returns on null), Assets upload would `POST /workspaces/null/assets` → 404, and the other pages render as null-keyed dead-ends.
- `GeneratePage`'s empty-state gate is `if (workspace && !corpusReady)` — it only handles "workspace exists but empty corpus", not "no workspace".

## Design

### 1. Route gate — `RequireWorkspace` (`client/src/App.tsx`)

A small wrapper mirroring the existing `RequireAuth`:

- Reads `useActiveWorkspace().hasNone`. When true, returns `<Navigate to="/setup" replace />`; otherwise renders `children`.
- Because `hasNone` is already `!isLoading && !isError`-guarded, the gate does **not** redirect during the initial workspaces fetch (page renders its own skeleton) nor on a server error (page renders its own error state).

Wraps the five **action** routes: `generate`, `history`, `assets`, `templates`, `settings`.
Leaves **ungated**: `index` (Dashboard) and `setup` — so there's no redirect loop and existing owners can still reach `/setup` to create *additional* workspaces from the switcher.

### 2. Dashboard first-run CTA (`client/src/features/dashboard/DashboardPage.tsx`)

When `hasNone`, render a "Create your first workspace" card (a CTA linking to `/setup`) in place of the stat grid + action cards. This is the soft landing — distinct from the `isError` banner already shipped in Phase 6 PR-B. Precedence: `isError` banner (existing) → else `hasNone` CTA → else the normal stat/action grid.

### 3. Belt-and-suspenders (minimal)

- **Assets upload submit** gets `disabled={!workspaceId}` — closes the one real rough edge (a `POST /workspaces/null/...` during the brief pre-resolve window).
- **Generate** needs no change: `generate()` already early-returns on a null `workspaceId`, so it is a safe no-op. Threading `workspaceId` through `ControlsPanel` would add surface for no gain.

## Error / edge handling

- **Loading:** `hasNone` is false while `useWorkspaces` loads → no premature redirect; the page shows its own skeleton until workspaces resolve.
- **Server error:** `hasNone` is false on `isError` → no false redirect to `/setup`; the page's existing error state (e.g. the Dashboard banner, Assets "Couldn't load assets") shows instead.
- **Last workspace deleted while on an action page:** `hasNone` flips true on the next render → the gate redirects to `/setup`. Expected.
- **Just created first workspace:** `WorkspaceSetupPage.createWorkspace()` calls `setActive(ws.id)`; `hasNone` flips false → action routes become reachable. No loop.

## Testing (vitest only)

- `RequireWorkspace`: redirects to `/setup` when `hasNone`; renders children when a workspace exists; does **not** redirect while loading or on error.
- `DashboardPage`: renders the first-run CTA when `hasNone`, and the normal grid otherwise.

## Out of scope

- Any server-side change.
- Disabling/hiding sidebar nav links when `hasNone` (the redirect already handles those clicks).
- Auto-bootstrapping a default workspace on account creation (the `/setup` stepper intentionally collects brand info first).
