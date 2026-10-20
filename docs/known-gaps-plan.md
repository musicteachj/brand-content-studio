# Known gaps plan (October 2026)

> **Status: planned (2026-10-20).** Follow-up to the October QA pass (`docs/QA-2026-10.md`, on branch `qa/2026-10-bug-bash`). All 17 findings there are fixed (PRs #58 to #65). This plan covers the two gaps the QA pass listed as still open, plus one High found while planning them. When a step ships, its decision lands in [`DECISIONS.md`](./DECISIONS.md), which stays the source of truth; this doc records the plan and the reasoning.

Order: **0 → 1 → 2**, each on its own branch off `dev` with its own PR. Step 2 depends on step 0 (a CSP can only be checked against the production build). Every step follows the usual loop: tests first, full gate, live check in the browser, `/code-review` and `/security-review`, and the owner's go-ahead before each commit, push, and PR.

## Decisions taken (owner, 2026-10-20)

| Gap | Choice | Rejected |
|---|---|---|
| Demo quota misses non-saving AI routes | **One AI-call counter**: every paid model route consumes from one per-account daily count | A second side counter with its own limit; a cost-weighted budget |
| No CSP | **Enforce after browser QA**, with a setting to fall back to report-only | Report-only first; defer to the deploy phase |

## Step 0: the production build serves a blank page (High, new)

**Found while planning step 2.** With `ENVIRONMENT=production` (the Docker image), `server/app/main.py` mounts `dist` at `/static` and answers every other path with `index.html`. Vite builds with the default base, so `index.html` loads `/assets/index-*.js` and `/assets/index-*.css`; both come back as `index.html` with `text/html`. The browser refuses them ("Expected a JavaScript module script but the server responded with a MIME type of text/html"), and `#root` stays empty. Reproduced locally on 2026-10-20 (production mode on port 8010, Playwright shows 0 children in `#root` and both MIME errors). CI's docker job only checks that `/` contains `id="root"`, so it passes. The QA pass ran on the Vite dev server, which serves assets itself, so it never saw this. Nothing is deployed yet.

**Fix (as built):** `server/app/spa.py`, `mount_spa(app, dist_dir)`, called last in `main.py` when `ENVIRONMENT=production`. It mounts one `StaticFiles` subclass at `/`, so HEAD, threadpool file lookups, and the path-traversal guard come from Starlette:
- Real files in `dist` are served as files. Hashed Vite output (`<name>-<8-char hash>.<ext>`) gets `Cache-Control: public, max-age=31536000, immutable`.
- Any other path is a client route and gets `index.html` with `Cache-Control: no-cache`, including `/assets` and `/assets/` (also the Assets page). So is `/index.html` by name, so a deploy's new hashes load at once.
- A missing hashed bundle file is a real 404, not the SPA.
- An unknown `/api/...` path (any method, any case) is a JSON 404.
- Dotfiles are never served.
- Font types (`woff2`, `woff`, `ttf`) are registered, since slim images have no `/etc/mime.types`.
- The unused `/static` mount is gone.

**Tests:** `server/tests/test_spa.py` (15) on a temporary `dist`: JS, CSS, and font content types; immutable versus no-cache; a missing bundle 404; client routes, HEAD, and the `/assets/` collision; API 404s for any method and case; dotfiles and traversal; a `dist` without an `assets` folder still starts.

**CI:** the docker job also fetches the JS file `index.html` references and asserts a JavaScript content type, and asserts `/api/nope` is a 404.

**Live:** build and run the image, then sign in as demo and load every page in Playwright.

## Step 1: one AI-call counter for the demo quota

**Gap.** `enforce_demo_generation_quota` counts the demo account's saved generations for the UTC day (cap `demo_daily_generation_limit`, 50). Brand extract, template "Draft with AI", and fill-from-document make paid model calls but save nothing, so they are bounded only by the per-IP rate limit. Many visitors can spend without limit on those three routes.

**Design:**
- **Storage:** a new `usage` collection, one document per account per UTC day: `{_id: "<user_id>:<YYYY-MM-DD>", user_id, day, count, expires_at}`. A TTL index on `expires_at` (about two days out) removes old documents.
- **Admission:** a new dependency, `enforce_demo_ai_quota`, replaces `enforce_demo_generation_quota` on all seven paid routes (text, card, LinkedIn post, document, brand extract, AI fill, fill-from-document). It admits a request with one atomic upsert: `update_one({_id, count: {$lt: limit}}, {$inc: {count: 1}, $setOnInsert: {...}}, upsert=True)`. When the day's document is already at the limit, the filter misses and the upsert hits the existing `_id`, which raises `DuplicateKeyError`. That error means "limit reached" and returns the same readable 429. Concurrent requests can't overshoot, because the check and the increment are one write.
- **Charged on admission, before the model call; not refunded on failure.** This is the spend-safe and simple choice. A request that the route then rejects (for example the empty-corpus 409) still costs one unit. Acceptable for a 50-a-day demo cap; noted in DECISIONS.
- **Settings:** the setting keeps its name (`demo_daily_generation_limit`), so no env or config churn. Its docstring and the 429 message now say "AI actions" rather than "generations".
- **Indexes:** the `generations (owner_id, created_at)` index only backed the old count. Drop it from `ensure_indexes` unless something else turns out to use it (check first).
- **Non-demo accounts** are unaffected, as today.

**Tests (server):**
- Each of the seven routes consumes exactly one unit.
- At the limit, every route answers 429 before the fake model service is called.
- `asyncio.gather` of limit + 5 concurrent admissions lets exactly `limit` through.
- A new UTC day starts at zero (clock patched).
- Non-demo users are never counted.
- `ensure_indexes` creates the TTL index.

**Docs:** a DECISIONS entry (#35), the `usage` collection in `DATA_MODEL.md`, the quota line in `ARCHITECTURE.md`, and the AUDIT residual note closed.

**Live:** set the limit to 3 by env. Use brand extract, AI fill, and a text post once each, then confirm the fourth action shows the 429 message in the UI.

## Step 2: an enforcing Content-Security-Policy

**Gap.** There's no CSP (AUDIT SEC-11 note; QA row H3). `SecurityHeadersMiddleware` already sets `nosniff`, `X-Frame-Options`, `Referrer-Policy`, and HSTS in production.

**What the app needs, found so far:**
- resvg (card PNG export) and satori (yoga) are WebAssembly, so `script-src` needs `'wasm-unsafe-eval'`.
- Radix dialogs inject a `<style>` element for scroll locking (`react-style-singleton`), so `style-src` needs `'unsafe-inline'` or a nonce. React `style={...}` props go through the CSSOM and don't need it.
- Card fonts load from `cdn.jsdelivr.net`, through `fetch` (bytes for satori) and CSSOM `FontFace`. Unsplash previews (`images.unsplash.com`) are fetched into data URLs.
- Data and blob URLs are used for images (card previews, export).

**Draft policy** (tightened by the browser pass below):
```
default-src 'self';
script-src 'self' 'wasm-unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob: https://images.unsplash.com;
font-src 'self' data: https://cdn.jsdelivr.net;
connect-src 'self' https://cdn.jsdelivr.net https://images.unsplash.com;
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

**Where it's set:**
- **Header:** `SecurityHeadersMiddleware`, on every response. JSON and SSE responses are unaffected by a CSP. The header is only rewritten at response start, so streaming is untouched.
- **Setting:** `csp_mode` = `enforce` (default) | `report-only` | `off`, so a regression after deploy can be eased off without a code change.
- **Dev:** the Vite dev server sends no CSP, so it's only exercised on the production build (step 0).

**Style nonce, considered and declined for now.** Removing `'unsafe-inline'` from `style-src` would mean templating `index.html` per request with a nonce and calling Radix's `setNonce` at boot. The script side, which is what blocks XSS exfiltration, is already strict without it. Revisit if a later audit asks.

**Browser QA (the gate for enforcing):** Playwright against the production build, with a listener on `securitypolicyviolation` events and console "Refused to" messages. The run fails on any violation. It walks every flow:
- sign in (demo and owner);
- each Generate mode, with card PNG export (wasm) and an uploaded-font card;
- the image picker (Unsplash search, brand images, upload);
- History detail and downloads;
- Templates upload, fill, and download;
- Settings (brand extract, fonts, dialogs);
- theme switching.

**Tests (server):** the header and its directives are present; `report-only` and `off` switch the header name or drop it; an SSE route still streams with the header set.

**Docs:** a DECISIONS entry (#36), the security headers section in `ARCHITECTURE.md`, the AUDIT SEC-11 note closed, and the `SecurityHeadersMiddleware` docstring updated.

## After this plan

Deploy items stay deferred to the AWS phase (`PLAN.md`): HSTS at the edge, per-IP rate-limit keying behind the load balancer (QA R2), and Docker/production hardening. Separately noted cleanups: deleting a generation leaves its built document files in storage; the starlette 1.x `HTTP_413`/`HTTP_422` constant renames; client dev-tool majors (vite 8, vitest 5, tailwind 4).
