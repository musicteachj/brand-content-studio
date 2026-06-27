# First-run / Zero-Workspace Onboarding Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guide a signed-in owner with **no workspaces** to the `/setup` stepper instead of dead-end, null-keyed action pages.

**Architecture:** Client-only (the server already 404-enforces a real, owned workspace). A `RequireWorkspace` route gate — mirroring the existing `RequireAuth` — redirects the five workspace-dependent routes to `/setup` when `useActiveWorkspace().hasNone` is true; the Dashboard gains a first-run CTA; the Assets upload submit is disabled when there's no workspace. No backend change.

**Tech Stack:** React + react-router-dom + react-query; Vitest (jsdom) for tests. Run client commands from `client/` using `./node_modules/.bin/<tool>` (the `client/vite.config.ts` test env is jsdom).

**Spec:** `docs/superpowers/specs/2026-06-27-onboarding-no-workspace-design.md`

**Branch:** `feat/onboarding-no-workspace` (off `dev`, already created).

**File structure:**
- Create: `client/src/features/workspace/RequireWorkspace.tsx` — the route gate (one responsibility).
- Create: `client/src/features/workspace/RequireWorkspace.test.tsx` — gate tests.
- Modify: `client/src/App.tsx` — wrap the five action routes with `RequireWorkspace`.
- Modify: `client/src/features/dashboard/DashboardPage.tsx` — first-run CTA when `hasNone`.
- Create: `client/src/features/dashboard/DashboardPage.test.tsx` — CTA test.
- Modify: `client/src/features/assets/AssetsPage.tsx` — disable upload submit when `!workspaceId`.
- Docs: `docs/DECISIONS.md`, `CHANGELOG.md`.

---

### Task 1: `RequireWorkspace` route gate

**Files:**
- Create: `client/src/features/workspace/RequireWorkspace.tsx`
- Test: `client/src/features/workspace/RequireWorkspace.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/features/workspace/RequireWorkspace.test.tsx`:

```tsx
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const { useActiveWorkspaceMock } = vi.hoisted(() => ({ useActiveWorkspaceMock: vi.fn() }));
vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: useActiveWorkspaceMock,
}));

import { RequireWorkspace } from "./RequireWorkspace";

let container: HTMLDivElement;
let root: Root;

function mountAt(path: string) {
  container = document.createElement("div");
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/assets"
            element={
              <RequireWorkspace>
                <div>ASSETS</div>
              </RequireWorkspace>
            }
          />
          <Route path="/setup" element={<div>SETUP</div>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

beforeEach(() => {
  useActiveWorkspaceMock.mockReset();
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

describe("RequireWorkspace", () => {
  it("redirects to /setup when the owner has no workspaces", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: true });
    mountAt("/assets");
    expect(container.textContent).toContain("SETUP");
  });

  it("renders children when a workspace exists", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: false });
    mountAt("/assets");
    expect(container.textContent).toContain("ASSETS");
  });

  it("does not redirect while loading or on error (hasNone is false)", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: false });
    mountAt("/assets");
    expect(container.textContent).toContain("ASSETS");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/features/workspace/RequireWorkspace.test.tsx`
Expected: FAIL — `RequireWorkspace` doesn't exist yet (import error).

- [ ] **Step 3: Create `client/src/features/workspace/RequireWorkspace.tsx`**

```tsx
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";

/** Gate for workspace-dependent pages: a signed-in owner with no workspaces is
 *  sent to the setup stepper instead of a dead-end, null-keyed page. The
 *  Dashboard and /setup stay ungated. `hasNone` is already `!isLoading &&
 *  !isError`, so this never redirects mid-fetch or on a server error. */
export function RequireWorkspace({ children }: { children: ReactNode }) {
  const { hasNone } = useActiveWorkspace();
  return hasNone ? <Navigate to="/setup" replace /> : <>{children}</>;
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/features/workspace/RequireWorkspace.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add client/src/features/workspace/RequireWorkspace.tsx client/src/features/workspace/RequireWorkspace.test.tsx
git commit -m "feat(onboarding): RequireWorkspace gate — redirect to /setup when hasNone"
```

---

### Task 2: Wire the gate into `App.tsx` + disable Assets upload when no workspace

**Files:**
- Modify: `client/src/App.tsx`
- Modify: `client/src/features/assets/AssetsPage.tsx`

- [ ] **Step 1: Import the gate** in `client/src/App.tsx` (after the `WorkspaceSetupPage` import):

```tsx
import { RequireWorkspace } from "@/features/workspace/RequireWorkspace";
```

- [ ] **Step 2: Wrap the five action routes** in `client/src/App.tsx`. Replace the five route lines (`generate`, `history`, `assets`, `templates`, `settings`) with:

```tsx
        <Route
          path="generate"
          element={
            <RequireWorkspace>
              <GeneratePage />
            </RequireWorkspace>
          }
        />
        <Route
          path="history"
          element={
            <RequireWorkspace>
              <HistoryPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="assets"
          element={
            <RequireWorkspace>
              <AssetsPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="templates"
          element={
            <RequireWorkspace>
              <TemplatesPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="settings"
          element={
            <RequireWorkspace>
              <SettingsPage />
            </RequireWorkspace>
          }
        />
```

Leave the `index` (Dashboard) and `setup` routes unwrapped.

- [ ] **Step 3: Disable the Assets upload submit when there's no workspace.** In `client/src/features/assets/AssetsPage.tsx`, find the `UploadCard` submit button:

```tsx
        <Button onClick={submit} disabled={!file || upload.isPending} loading={upload.isPending}>
```

Replace with:

```tsx
        <Button
          onClick={submit}
          disabled={!file || !workspaceId || upload.isPending}
          loading={upload.isPending}
        >
```

(`workspaceId` is already a prop of `UploadCard`.)

- [ ] **Step 4: Typecheck + lint + format**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}"`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add client/src/App.tsx client/src/features/assets/AssetsPage.tsx
git commit -m "feat(onboarding): gate action routes + disable upload when no workspace"
```

---

### Task 3: Dashboard first-run CTA

**Files:**
- Modify: `client/src/features/dashboard/DashboardPage.tsx`
- Test: `client/src/features/dashboard/DashboardPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/features/dashboard/DashboardPage.test.tsx`:

```tsx
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const { useActiveWorkspaceMock, useGenerationCountMock } = vi.hoisted(() => ({
  useActiveWorkspaceMock: vi.fn(),
  useGenerationCountMock: vi.fn(),
}));
vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: useActiveWorkspaceMock,
}));
vi.mock("@/api/generations", () => ({ useGenerationCount: useGenerationCountMock }));
vi.mock("@/stores/auth", () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { full_name: "Jane Doe" } }) }));

import { DashboardPage } from "./DashboardPage";

let container: HTMLDivElement;
let root: Root;

function mount() {
  container = document.createElement("div");
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    ),
  );
}

beforeEach(() => {
  useGenerationCountMock.mockReturnValue({ data: 0 });
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.clearAllMocks();
});

describe("DashboardPage first-run", () => {
  it("shows the create-workspace CTA when the owner has no workspaces", () => {
    useActiveWorkspaceMock.mockReturnValue({ workspace: undefined, workspaceId: null, isError: false, hasNone: true });
    mount();
    expect(container.textContent).toContain("Create your first workspace");
    expect(container.textContent).not.toContain("Brand assets");
  });

  it("shows the stat grid when a workspace exists", () => {
    useActiveWorkspaceMock.mockReturnValue({
      workspace: { asset_count: 2, ready_chunk_count: 5 },
      workspaceId: "a",
      isError: false,
      hasNone: false,
    });
    mount();
    expect(container.textContent).toContain("Brand assets");
    expect(container.textContent).not.toContain("Create your first workspace");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/features/dashboard/DashboardPage.test.tsx`
Expected: FAIL — the CTA text isn't rendered (and `hasNone` isn't read), so the first test fails.

- [ ] **Step 3: Pull `hasNone` from the hook.** In `client/src/features/dashboard/DashboardPage.tsx`, change:

```tsx
  const { workspace, workspaceId, isError } = useActiveWorkspace();
```

to:

```tsx
  const { workspace, workspaceId, isError, hasNone } = useActiveWorkspace();
```

- [ ] **Step 4: Render the CTA in place of the grids when `hasNone`.** In `client/src/features/dashboard/DashboardPage.tsx`, replace the two grid `<div>` blocks (the `sm:grid-cols-3` stat grid and the `sm:grid-cols-2` action grid) with a `hasNone` branch:

```tsx
      {hasNone ? (
        <div
          className="animate-fade-in-up rounded-lg border border-border bg-surface p-8 text-center shadow-light"
          style={{ animationDelay: "60ms" }}
        >
          <h2 className="text-base font-semibold text-foreground">Create your first workspace</h2>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted-foreground">
            A workspace holds one brand's corpus and generations. Create one to start ingesting
            assets and generating on-brand content.
          </p>
          <Button className="mt-5" onClick={() => navigate("/setup")}>
            Create workspace
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      ) : (
        <>
          <div
            className="grid animate-fade-in-up gap-4 sm:grid-cols-3"
            style={{ animationDelay: "60ms" }}
          >
            <StatCard
              label="Brand assets"
              value={String(workspace?.asset_count ?? 0)}
              hint="Ingested documents"
            />
            <StatCard
              label="Ready chunks"
              value={String(workspace?.ready_chunk_count ?? 0)}
              hint="Retrievable corpus"
            />
            <StatCard
              label="Generations"
              value={String(generationCount ?? 0)}
              hint="Posts + cards"
            />
          </div>

          <div
            className="grid animate-fade-in-up gap-4 sm:grid-cols-2"
            style={{ animationDelay: "120ms" }}
          >
            <ActionCard
              icon={FileText}
              title="Ingest brand assets"
              body="Upload voice guides and past posts to build the retrievable corpus."
              cta="Open Asset Manager"
              onClick={() => navigate("/assets")}
            />
            <ActionCard
              icon={PenLine}
              title="Generate content"
              body="Write an on-brand LinkedIn post or designed card from a brief."
              cta="Open Generate"
              primary
              onClick={() => navigate("/generate")}
            />
          </div>
        </>
      )}
```

(`Button`, `ArrowRight`, `FileText`, `PenLine`, `StatCard`, `ActionCard`, `navigate`, and `generationCount` are all already in scope in this file.)

- [ ] **Step 5: Run it to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/features/dashboard/DashboardPage.test.tsx`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add client/src/features/dashboard/DashboardPage.tsx client/src/features/dashboard/DashboardPage.test.tsx
git commit -m "feat(onboarding): Dashboard first-run create-workspace CTA"
```

---

### Task 4: Client gate + docs

**Files:**
- Modify: `docs/DECISIONS.md`, `CHANGELOG.md`

- [ ] **Step 1: Full client gate**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --check "src/**/*.{ts,tsx}" && ./node_modules/.bin/vitest run && ./node_modules/.bin/vite build`
Expected: all green (vitest +5: 3 gate + 2 dashboard).

- [ ] **Step 2: Add DECISIONS entry #27.** In `docs/DECISIONS.md`, add a row after the `#26` row:

```
| 27 | Zero-workspace onboarding gate | A signed-in owner with **no workspaces** is routed to `/setup` rather than dead-end action pages. A `RequireWorkspace` gate (mirrors `RequireAuth`) wraps the five workspace-dependent routes (`generate`/`history`/`assets`/`templates`/`settings`) and `<Navigate to="/setup">` when `useActiveWorkspace().hasNone`; the **Dashboard** and `/setup` stay ungated (soft landing + no redirect loop). The Dashboard shows a first-run "Create your first workspace" CTA; the Assets upload submit is disabled when `workspaceId` is null. **Client-only** — every workspace-scoped route already 404s without an owned workspace via `get_workspace_or_404`, so this closes a UX gap, not a security one. The gap only surfaced once real (non-demo) owner accounts existed: the demo user always owns the seeded Verdure workspace. | a fresh owner account starts with zero workspaces and the existing UI rendered null-keyed dead-ends (Generate no-op, upload → `/workspaces/null/...` 404); `hasNone` was computed but never consumed | The server already enforces the invariant, so the fix belongs in routing/UX; reusing the existing `hasNone` signal + the `RequireAuth` pattern keeps it minimal and consistent. |
```

- [ ] **Step 3: Add CHANGELOG entry.** In `CHANGELOG.md`, under `## [Unreleased]`, add at the top:

```markdown
### Added — Zero-workspace onboarding gate

A signed-in owner with no workspaces is now guided to the `/setup` stepper instead of landing on dead-end, null-keyed action pages (a gap exposed by real non-demo owner accounts, which start with zero workspaces). A `RequireWorkspace` route gate redirects the five workspace-dependent routes (`generate`/`history`/`assets`/`templates`/`settings`) to `/setup` when there are no workspaces; the Dashboard and `/setup` stay reachable. The Dashboard gains a first-run "Create your first workspace" CTA, and the Assets upload submit is disabled until a workspace exists. Client-only — the server already 404-enforces an owned workspace. See [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#27). Tests: vitest (+5) — the gate's redirect/render/loading branches and the Dashboard CTA.
```

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md CHANGELOG.md
git commit -m "docs(onboarding): zero-workspace gate — DECISIONS #27 + CHANGELOG"
```

---

### Task 5: Review, verify, PR

- [ ] **Step 1: Re-run the client gate** (Task 4 Step 1) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: client-only routing change; the server-side authorization is unchanged and already enforces the invariant.)
- [ ] **Step 4: Live verify (owner):** sign in as the fresh owner with no workspaces → every action route (Generate/Assets/History/Templates/Settings) redirects to `/setup`; the Dashboard shows the "Create your first workspace" CTA. Create a workspace → the redirect stops and all pages render normally. Switch back to an account/workspace that exists → no spurious redirects.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/onboarding-no-workspace` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** route gate on the five action routes (Task 1+2) ✓; Dashboard/`setup` ungated (Task 2, leaves `index`/`setup` unwrapped) ✓; Dashboard first-run CTA with stated precedence — `isError` banner untouched above the `hasNone` branch (Task 3) ✓; Assets upload `disabled={!workspaceId}` (Task 2) ✓; Generate unchanged (relies on existing null early-return — no task, per spec) ✓; loading/error don't redirect (Task 1 test asserts render-children when `hasNone` false) ✓; tests vitest-only (Tasks 1, 3) ✓; no server change ✓; docs (Task 4) ✓.

**Placeholder scan:** none — every code step is concrete.

**Type consistency:** `RequireWorkspace({ children }: { children: ReactNode })` matches its import + usage in `App.tsx` (Task 2). `useActiveWorkspace().hasNone` matches the hook's actual return (it already exposes `hasNone`). The Dashboard destructure adds `hasNone` to the existing `{ workspace, workspaceId, isError }` (Task 3). Test mocks return only the fields each component reads (`hasNone` for the gate; `workspace`/`workspaceId`/`isError`/`hasNone` for the Dashboard).
