# Development Workflow

> How we actually build Brand Content Studio — slice strategy, front/back ordering, branching, commits, and definition of done. Pairs with the phased roadmap in [PLAN.md](./PLAN.md) (what to build, in what order) and follows [DECISIONS.md](./DECISIONS.md).

---

## 1. Slice strategy — vertical slices by capability

We build **one capability end-to-end at a time** (backend + frontend + tests), not one layer at a time and not one view at a time.

- ❌ Not "all backend, then all frontend."
- ❌ Not "build all 10 views, then wire them up."
- ✅ Each [PLAN.md](./PLAN.md) phase is a vertical slice that produces a *working capability* with its own acceptance criterion. Phase 1a = text posts working end-to-end; Phase 1b = image cards working end-to-end.

A slice may touch two or three views, but we build only the **minimum view a slice needs** to hit its acceptance criterion, then enrich later. The landing page is built last (after the app works), per the spec.

### Views by phase

| Phase | Views built / touched |
|---|---|
| 0 — Scaffold | AppShell + SideNav, Login (demo button) — minimal shell only |
| 1a — Text posts | Workspace Setup (name + asset upload steps), Asset Manager, Generate (text mode + Retrieval Debug Panel), Content History (basic), Dashboard (basic) |
| 1b — Image cards | Generate (card mode: template picker, Image Picker panel, Card Preview, export); Content History thumbnails render cards |
| 1.5 — Customization | Generate enhancements (inline edit, image/layout swap, accent toggle); Settings (quiet page, slot in here) |
| 2 — Documents | Document output controls in Generate / a documents view |
| Deploy | none (infra only) |
| Last | Landing page |

---

## 2. The slice loop (repeat per feature)

1. **Contract first.** Define the API request/response shape as a Pydantic v2 model (`server/app/models`) and a matching TypeScript type (`client/src/types`). This keeps front and back from diverging.
2. **Backend.** Implement the route + service; write pytest (unit + the RAG tests named in [PLAN.md](./PLAN.md): chunking, ingestion-ready, `test_query_is_workspace_scoped`, streaming-persists). Backend goes first because the UI exists to display real RAG output — build the data, then the view.
3. **Frontend.** Wire the view to the **real** endpoint (react-query hook, or the `lib/sse.ts` reader for streaming). Build the UI with the Claude **design skills** (`frontend-design` / `impeccable` / `ui-ux-pro-max`); the [`mocks/`](./mocks/) and [`DESIGN.md`](./DESIGN.md) are a **reference, not a pixel-exact spec** — take a better UI/UX option when a skill offers one, and fold the improvement back into `DESIGN.md`. Keep Folio's tokens as the baseline; never hardcode hex.
4. **Polish to design.** Loading/empty/error states, accessibility (focus rings, `aria-live` on the streaming preview, icon+label status), motion gated behind `prefers-reduced-motion` — all per [DESIGN.md](./DESIGN.md).
5. **Verify & PR.** Run the slice's tests + check it against the phase's acceptance criterion, then open a PR into `dev`.

Frontend view *shells* may be scaffolded from the mocks in parallel with backend work, but they're **wired last** — against the real contract, not a guess.

---

## 3. Branching

```
main  ──────●────────────────●───────────────●──────   stable / releasable; tag phase completions
             \              /  \             /
dev   ────●───●──●──●──●──●─────●──●──●──●──●────────   integration branch (current branch)
           \  /     \  /            \  /
feat/*      ●●        ●●              ●●                short-lived feature branches
```

- **`main`** — stable, releasable. Only receives merges from `dev` at phase boundaries. Tag each phase on `main`: `v0.0.0` (scaffold), `v0.1.0` (Phase 1a), `v0.2.0` (1b), etc. — matching the version mapping in [`../CHANGELOG.md`](../CHANGELOG.md).
- **`dev`** — integration branch (where we are now). Feature branches merge here; it should always at least build.
- **`feat/<phase>-<slice>`** — short-lived, branched off `dev`, one per feature. Examples: `feat/0-scaffold`, `feat/1a-ingestion`, `feat/1a-text-generation`, `feat/1b-card-export`.
- Other prefixes as needed: `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.

**Flow:** branch off `dev` → build the slice → PR into `dev` → at phase boundary, PR `dev` → `main` + tag.

> The current planning docs can land directly on `dev` as a `docs:` commit (foundational baseline). Feature work starts on `feat/*` branches from Phase 0 onward.

---

## 4. Commits

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`.

- **Types:** `feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `build`, `perf`.
- **Scope (optional):** `client`, `server`, `rag`, `design`.
- Small, logical commits — one concern each. Don't bundle a refactor with a feature.
- End commit messages with the `Co-Authored-By` trailer.

Examples:
```
feat(rag): add Chroma VectorStore implementation behind protocol
feat(server): stream text-post generation over SSE with retrieval meta
test(rag): assert query is scoped to workspace (no cross-leak)
feat(client): wire Generate page to /generate/text SSE stream
docs: reconcile spec + AWS plan, add docs/ planning set
```

---

## 5. Before any push — mandatory review gate

**Nothing is ever pushed until both `/code-review` and `/security-review` have run on the changes and their findings are addressed.** This is the non-negotiable floor for *every* push — enforced by the approval prompt on `git push` (see `.claude/settings.json`). The tiers below only change *how deep* the reviews go, never *whether* they run.

Order is always: **reviews → fix → ask → push.** Claude must not request push approval until both reviews have run on the current changes, and never pushes unilaterally (every commit/push needs explicit approval).

### Review depth by risk

| Tier | When | Code review | Security review |
|---|---|---|---|
| **1 — default** | most slices; docs-only | `/code-review` **medium** | `/security-review` **light** (focus: secrets/keys, obvious issues) |
| **2 — sensitive surface** | diff touches a surface below | `/code-review` **high** | `/security-review` **full** |
| **3 — phase boundary / milestone** | `dev` → `main`, before tagging or first deploy | `/code-review` **high–max** across the whole phase diff | `/security-review` **full** + **you** run `/code-review ultra` (cloud multi-agent; billed, user-triggered — Claude can't launch it) |

**Sensitive surfaces (escalate to Tier 2):** auth (JWT, demo bypass, `get_workspace_or_404` ownership) · workspace/retrieval isolation (the Qdrant filter is the only tenant boundary — a cross-workspace leak is the top risk) · file upload + ingestion (untrusted PDF parsing, `storage_key` path traversal, type/size limits) · external calls (Unsplash proxy SSRF, API-key exposure) · secrets/config (`.env`, Secrets Manager) · new dependencies.

**RAG/AI-specific items to check explicitly** (generic reviewers miss these):
- **Prompt injection via ingested content** — a malicious uploaded brand doc can carry instructions into the generation prompt; check how retrieved chunks are framed.
- **Retrieval scoping** — every query workspace-filtered, with a passing `test_query_is_workspace_scoped`.

### Mechanics
- **Fix loop:** fix every finding, or consciously accept it with a one-line reason in the PR; re-run the relevant review after material changes. Use `/code-review --fix` only with an eyeball of the applied diff; `/simplify` for pure cleanup, not bug-hunting.
- **Paper trail:** record the outcome in the PR description (e.g. "code-review: 2 fixed; security-review: clean").
- **Where reviews run:** on the local diff before the first push of a branch (you must push before opening its PR); they may be re-run on the PR.
- **CI (deploy phase):** GitHub Actions runs the quality gate on every PR — `ruff` + `mypy` + `pytest` (server) and `eslint` + `prettier --check` + `tsc --noEmit` + build (client) — so the automated half stops depending on memory.

---

## 6. Pull requests & merging

- Every `feat/*` branch merges into `dev` via PR — even solo, the PR is the portfolio narrative and the future CI gate.
- **Self-review checklist** before merging a PR into `dev`:
  - [ ] Backend tests pass (pytest), including the relevant RAG tests.
  - [ ] Wired to the real endpoint (no leftover mocks/stubs).
  - [ ] Matches the design: no hardcoded hex, states covered, a11y basics, card preview uses workspace fonts (not app fonts).
  - [ ] The phase/slice acceptance criterion is demonstrably met.
  - [ ] `/code-review` and `/security-review` were run and findings addressed (the §5 gate) before the branch was pushed.
  - [ ] Quality gate clean: `ruff` + `mypy` (server), `eslint` + `prettier --check` + `tsc --noEmit` (client).
- **Squash-merge** `feat/*` → `dev` to keep `dev` history readable; use a merge commit for `dev` → `main` so release points are visible.
- **CI (added in the deploy phase):** run pytest + client build on every PR; later, build/push the Docker image on merge to `main`.

---

## 7. Definition of done

**A slice is done when:** its tests are green, it's wired to the real endpoint, it covers the design's loading/empty/error states, and its acceptance bullet is met.

**A phase is done when:** all its slices are merged to `dev`, the phase acceptance criteria in [PLAN.md](./PLAN.md) pass end-to-end (`docker-compose up` + `npm run dev`), [`../CHANGELOG.md`](../CHANGELOG.md) has an entry for the phase, and `dev` is merged to `main` and tagged.

**Any push is allowed only after:** the §5 review gate (`/code-review` + `/security-review`, findings addressed) and explicit push approval.
