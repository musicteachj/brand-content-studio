# Folio: Demo Sessions and Deploy Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Folio ready to open to the public with one click: private 24-hour visitor sessions behind Turnstile, a dollar ledger that caps every AI call, read-only examples as the free path, Chroma in-process, and a production image verified locally with Docker.

**Architecture:** The FastAPI server gains a Mongo-backed AI ledger (integer micro-dollars, atomic conditional updates, daily pacing) that every Claude and OpenAI call goes through. Streaming routes reserve the whole action before the SSE response starts, settle each call in a shielded `finally`, and send heartbeats. The demo start becomes a Turnstile-checked, per-IP-limited endpoint that creates a 24-hour session whose ID rides in the JWT and scopes every History read and write. Chroma runs in-process (`chromadb.PersistentClient`), and a self-healing seed, run inside the app process at startup, rebuilds the demo (including four read-only example generations) from checked-in fixtures with no paid calls.

**Tech Stack:** FastAPI 0.139 / Starlette 1.3, uvicorn (upgraded), Motor and MongoDB 7, chromadb 1.5.9, anthropic SDK 0.111, openai SDK 2.x, slowapi 0.1.10, React 19, Vite 8, Vitest 5, MSW 2, Docker.

**Spec:** `/Users/jameslittlefield/Documents/github_things/portfolio-infra/docs/design/2026-11-18-portfolio-apps-aws-deployment-design.md` (v2.1): sections 5.1, 5.2, 5.3, 5.4 (Folio), 5.10, 10. Shared conventions: `/Users/jameslittlefield/Documents/github_things/portfolio-infra/PLAN.md` ("Shared conventions"). Executors read both.

---

## Decisions for James before execution

The master plan says a conflict with the design is resolved by the design, and if the design looks wrong, stop and ask. These are the places this plan departs from, or fills a gap in, the design. Tasks that depend on one start with a stop.

| ID | Decision | Design says | Why | Affects |
|---|---|---|---|---|
| D1 (decided: accepted by James, 2026-11-19) | The seed runs **inside the app process at startup** (`SEED_ON_STARTUP=true`), not through ECS Exec. | 5.4: "Run it inside the running container (ECS Exec)." | `python -m seed.seed_demo` under ECS Exec is a second process on the Chroma data directory, which the in-process design forbids (two copies must never share it, 5.5). Startup seeding is in the same process, free (D2), and repairs a restored volume on its own. | Task 11, Phase 3 |
| D2 (decided: accepted by James, 2026-11-19) | Corpus embeddings come from a **checked-in fixture**, exported for free from James's existing local Chroma data. Only if that export is incomplete does it need one paid run (under $0.001, with OK). The production seed then makes **no paid call**. | 5.4: the seed "costs a few cents of embeddings, so it's a paid run." | Removes a paid step from Phase 3, makes the seed self-healing without an OpenAI key, and lets CI boot the real seed. Master plan Phase 3 item 3 would change to "free". | Tasks 8, 11, 18 |
| D3 | Retrieval (one query embedding) moves **before** the SSE response, so the model calls can be reserved from exact prompt sizes. Heartbeats then cover thinking, the structured call, and rendering, not retrieval. | Conventions list heartbeats "during retrieval". | Exact reservations keep the $0.15 visitor allowance usable; a static bound would reserve about $0.13 for a post. Retrieval is a sub-second call with a 10 s timeout. | Tasks 5, 6, 7 |
| D4 | Timeouts: structured calls 60 s; streamed calls 30 s between chunks and 90 s in total; embeddings 10 s; Turnstile 5 s. All settings. | Conventions: "below 30 s per call where the flow allows, and well below the ALB's 120 s". | A 4,000-token structured reply (`CARD_FIELDS_MAX_TOKENS`, `DOC_SECTIONS_MAX_TOKENS`, ai_service.py:29-31) can take close to a minute; a 30 s cap would turn slow but valid replies into billed failures. Heartbeats keep the ALB connection busy. | Task 3 |
| D5 | Keep `AI_VISITOR_BUDGET_USD=0.15`. Under the shared rule (admit while room is left, counted at settled cost; updated 2026-11-19) a visitor gets about 3 to 4 posts at typical cost. A post or document reserves about $0.11 against the day (caption: about 8,000 input tokens at $2 plus 4,000 output at $10; card or sections: about 6,000 input plus 4,000 output), but the visitor is charged only what settles. A card reserves about $0.08 and a text post about $0.06, so those fit two to four times, depending on actual costs, which are unmeasured (no paid runs). | 5.2: "$0.15 per visitor session, 2 or 3 generations". | Reservations must cover `max_tokens` in full (ai_service.py:26-31; generate.py:190, 200; documents.py:79, 88). Raising the allowance to $0.25 is an env change. | Task 4 (no code change) |
| D6 (decided by James, 2026-11-19: do NOT re-add; security fixes only through the GitHub setting) | Re-add `.github/dependabot.yml`. | 5.10 item 3: add it. | James removed it on purpose ("Not using Dependabot", commit 0b77272). The 2026-11-19 design reverses that; confirm. | Task 16 |

Other choices this plan makes inside the design's "left to the builder" space are listed in its Global Constraints and in each task.

---

## Global Constraints

Every task's requirements include these. Values are copied from the spec and the master plan.

- **Approval:** James approves every commit, push, merge, branch creation, and PR, one at a time. Every commit step reads "Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing." Commit messages are Conventional Commits (`type(scope): summary`, docs/WORKFLOW.md section 4) and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- **No paid calls:** no Anthropic, OpenAI, or other billed call anywhere without James's OK for that run. Tests use `FakeVectorStore` and `FakeGenerationService` (`server/tests/fakes.py`), the `FakeEmbedder` added in Task 6, a network guard (Task 3), and empty API keys as CI does (ci.yml:86-87). Cloudflare's Turnstile test keys are answered locally, never by siteverify.
- **Writing:** American English everywhere (code, comments, copy, docs, commits). No em dashes anywhere, including this plan, fixtures, and visitor copy. Task 11 adds a test that fails on an em dash in visitor copy and fixtures.
- **Env names and defaults:**
  - `AI_MONTHLY_BUDGET_USD=10`, `AI_PACING_MULTIPLIER=3`, `AI_DAILY_FLOOR_USD=0.50`, `AI_VISITOR_BUDGET_USD=0.15` (per visitor session, counting billed failures). `AI_MONTHLY_BUDGET_USD=0` means live AI off: every AI action is refused with the friendly free-path message.
  - `DEMO_STARTS_PER_HOUR=15`, `DEMO_STARTS_PER_DAY=50` (per IP).
  - `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`. Test keys: always-pass site key `1x00000000000000000000AA` with secret `1x0000000000000000000000000000000AA`; always-fail secret `2x0000000000000000000000000000000AA`; dummy token `XXXX.DUMMY.TOKEN.XXXX`. Re-check these against developers.cloudflare.com/turnstile/troubleshooting/testing/ before Task 9 (Open Door read them on 2026-11-11, open-door/apps/api/app/modules/sandbox/turnstile.py:37-40).
  - `FORWARDED_ALLOW_IPS` (never `*` or a `/0` network), `APP_ORIGIN`, `SEED_ON_STARTUP`, `CHROMA_PATH`, `DATABASE_NAME` (default becomes `folio`).
- **Pacing (UTC days and months):** `allowance_today = min(left_this_month, max(multiplier x left_this_month / days_left_including_today, floor))`; `left_this_month = budget - (settled + open reservations dated before today in this month)`. Admit only if today's (settled + open) plus the reservation is at most `allowance_today`. Never exceed the month.
- **Ledger:** its own collections (`ai_spend_days`, `ai_spend_calls`, `ai_spend_visitors`), never `usage` and never a TTL on spend. Integer micro-dollars. Atomic conditional updates, no lock across a model call. Settle each call from `usage` before raising (claude_calls.py:82-86 and :108-115 are billed). Keep the full reservation on timeout, connection error, cancellation, or unknown outcome. Settle to $0 on: 401, 403, 402, a 400 workspace or organization usage-limit error or a 400 saying the credit balance is too low, any 429 (plain rate limits included, shared rule update 2026-11-19), a 529 or overloaded error before any output. Sweeper charges reservations older than 10 minutes.
- **Prices (per million tokens):** Sonnet 5.5 (`claude-sonnet-5-5`) $2 input, $10 output, $0.10 cache read; Opus 5.5 $4 / $20; Haiku 5.5 $0.10 / $0.50; Opus 5 and 4.8 $5 / $25; `text-embedding-3-small` $0.02. In micro-dollars per token: Sonnet input 2, output 10.
- **Token estimate:** `ceil(utf8_bytes / 2)` per text (Open Door's safe bound, open-door/apps/api/app/ai/pricing.py:274-284), plus 5,000 tokens per image and 500 tokens for a structured-output schema.
- **Server:** uvicorn `--timeout-keep-alive 130`, `--proxy-headers`, `--timeout-graceful-shutdown 25` (graceful stop inside 30 s), one worker. Health: `/api/health/live` (no database) and `/api/health` (readiness, about 2 s timeouts, 503 on failure). Never a check outside `/api` (spa.py:36-46).
- **Containers:** uid 10001, `.dockerignore` excludes `.env` files, storage at `/app/storage` and Chroma at `/app/chroma`, both persistent volumes owned by uid 10001. Memory hard limit 1024 MiB.
- **Retention copy (exact):** "removed from the app after 24 hours; backups up to 7 days; server logs (including IP addresses) 14 days". Processors: Anthropic, OpenAI, Cloudflare, Unsplash, AWS, MongoDB Atlas.
- **Commands:**
  - Server gate (G-server): `docker compose up -d` then `cd server && .venv/bin/ruff check app tests && .venv/bin/mypy app && .venv/bin/python -m pytest -q`
  - Client gate (G-client): `cd client && npm run lint && npm run format && npm run build && npm test`
  - One server test: `cd server && .venv/bin/python -m pytest tests/<file>.py::<test> -q`; one client test file: `cd client && npx vitest run <path>`
- **CHANGELOG:** each task adds one `### <Kind>: <title>` entry under `[Unreleased]` in `CHANGELOG.md` (newest first, one paragraph, ending with a `Gate:` line that names the checks and the pytest and vitest counts), as earlier entries do.
- **Friendly copy (exact; each constant lives in `server/app/utils/errors.py`, added by the first task that uses it):**
  - `LIVE_AI_PAUSED_COPY = "Live generation is paused right now. Browse the ready-made examples to see what Folio makes."` (code `live_ai_paused`, HTTP 429)
  - `VISITOR_ALLOWANCE_COPY = "You've used this demo's live generations. Browse the ready-made examples, or start a new demo later."` (code `visitor_allowance`, 429)
  - `LIVE_AI_UNAVAILABLE_COPY = "Live generation isn't available right now. Browse the ready-made examples to see what Folio makes."` (code `live_ai_unavailable`, 503)
  - `RATE_LIMITED_COPY = "Too many requests from your network just now. Wait a minute and try again, or browse the ready-made examples."` (code `rate_limited`, 429)
  - `DEMO_ENDED_COPY = "Your demo session ended. Start a new one any time."` (code `demo_ended`, 401)
  - `BOT_CHECK_FAILED_COPY = "We couldn't confirm you're a person. Please try again."` (code `bot_check_failed`, 403)
  - `BOT_CHECK_UNAVAILABLE_COPY = "The bot check isn't responding right now. Try again in a moment, or browse the ready-made examples."` (code `bot_check_unavailable`, 503)
  - `EXAMPLE_READ_ONLY_COPY = "Examples are read-only. Generate your own to edit it."` (code `example_read_only`, 403)

## Review Focus

The five inputs most likely to bite a visitor that the spec implies but does not spell out. Each has a test in the owning task.

1. **One visitor, two tabs, two actions at once:** the day's allowance never overshoots, and the visitor allowance overshoots by at most the reservations already admitted while room remained (the shared "admit while room is left" rule). Tests `test_visitor_with_room_left_is_admitted_once_more_then_refused` and `test_concurrent_reservations_cannot_overshoot_the_day` (Task 4).
2. **A reservation that crosses UTC midnight or a month boundary:** it settles on the day it was reserved, and a new month starts with the full budget. Tests `test_settle_after_midnight_goes_to_the_reservation_day` and `test_a_new_utc_month_starts_with_the_full_budget` (Task 4).
3. **A token from before the deploy, or an expired or deleted session:** a clean 401 with `demo_ended` and the "start again" path, never a 500 or the hidden login page. Tests `test_a_demo_token_without_a_session_claim_is_demo_ended` (Task 9) and `test_a_401_logs_out_and_shows_the_demo_ended_banner` (Task 13).
4. **A data directory the app user can't write** (a root-owned host mount): the app refuses to start with a clear log line instead of failing after both paid calls (documents.py:115-118). Test `test_startup_refuses_an_unwritable_storage_dir` (Task 14).
5. **A partly lost volume** (files gone, Chroma empty, an example deleted): startup repairs it without a paid call, and readiness reports a seed that could not be repaired. Tests `test_seed_repairs_missing_files_collection_and_examples_without_paid_calls` (Task 11) and `test_readiness_is_503_when_the_seed_failed` (Task 14).

---

## File map

Created:
- `CLAUDE.md`: repo rules and pointers (Task 1).
- `server/app/services/ai_clients.py`: the one `AsyncAnthropic` and one `OpenAI` client (Task 3).
- `server/app/services/ai_pricing.py`: prices, token estimates, micro-dollar math (Task 4).
- `server/app/services/ai_ledger.py`: Mongo ledger, pacing, reserve, settle, sweep, snapshot (Task 4).
- `server/app/services/ai_meter.py`: `MeteredLine`, `MeteredAction`, `reserve_action`, `claude_line`, `embedding_line` (Task 4).
- `server/app/services/ai_failures.py`: which provider errors are unbilled, which are outages (Task 5).
- `server/app/routes/status.py`: public cached `GET /api/status` (Task 4, extended in Task 9).
- `server/app/jobs/cleanup.py`: hourly job: sweep, prune, expired sessions (Tasks 4, 10).
- `server/app/services/turnstile.py`: siteverify client and local test-key verifier (Task 9).
- `server/app/services/session_service.py`: demo sessions (Task 9).
- `server/app/routes/examples.py`: public read-only examples (Task 11).
- `server/seed/fixtures/verdure_embeddings.json`, `server/seed/fixtures/examples.json`, `server/seed/build_embeddings_fixture.py` (Tasks 8, 11).
- `docker-compose.prod.yml`: local production run (Task 14).
- `client/src/lib/turnstile.ts`, `client/src/api/status.ts`, `client/src/api/examples.ts`, `client/src/features/start/StartPage.tsx`, `client/src/features/examples/ExamplesPage.tsx`, `client/src/features/generate/GenerationError.tsx`, `client/src/features/privacy/PrivacyPage.tsx` (Tasks 9, 12, 13, 15).
- `.github/workflows/security.yml` (Task 16). No `dependabot.yml` (D6, James 2026-11-19).
- `docs/DEPLOY.md` (Task 17).

Deleted: `server/app/services/usage_service.py`, `server/tests/test_demo_ai_quota.py` (Task 5); `server/app/rag/qdrant_store.py` (Task 8).

---

### Task 1: Set up the work branch, commit this plan and CLAUDE.md

**Files:**
- Create: `CLAUDE.md`
- Commit: `docs/superpowers/plans/2026-11-19-demo-sessions-and-deploy-readiness.md` (this file, untracked in the working tree; untracked files move with checkouts)

**Interfaces:** Produces the branch `feat/portfolio-demo-readiness`, cut from a `dev` that equals `origin/dev` after `docs/readme-ai-settings` is merged.

- [ ] **Step 1: Confirm the start state**

Run: `git status --short && git fetch origin && git rev-parse --short HEAD && git rev-list --count origin/dev..docs/readme-ai-settings && git rev-list --count dev..origin/dev`
Expected: only `?? docs/superpowers/plans/2026-11-19-demo-sessions-and-deploy-readiness.md`; HEAD `acc0733`; `1`; `6` (or more if `origin/dev` moved; then recheck before continuing).

- [ ] **Step 2: Review the docs branch (docs/WORKFLOW.md section 5, tier 1)**

Run `/code-review medium` and `/security-review` (light) on `git diff origin/dev...docs/readme-ai-settings`. Fix nothing on this branch without a separate OK; note the outcome for the PR body.

- [ ] **Step 3: Open the PR into dev**

Run: `gh pr list --head docs/readme-ai-settings --state all`. If none is open, prepare `gh pr create --base dev --head docs/readme-ai-settings --title "docs: README settings for the Sonnet 5.5 move, plus two corrections" --body-file <tmp>` with a body summarizing the commit and the review outcome.
Stop: show the PR title and body, and wait for James's explicit OK before creating the PR.

- [ ] **Step 4: Wait for CI**

Run: `gh pr checks <number> --watch`
Expected: `client`, `server`, `docker`, and `audit` pass.

- [ ] **Step 5: Merge with a merge commit**

Stop: show the PR number and checks, and wait for James's explicit OK before merging.
Run: `gh pr merge <number> --merge`

- [ ] **Step 6: Bring local dev up to date**

Run: `git checkout dev && git pull --ff-only origin dev && git rev-list --count dev..origin/dev`
Expected: `0`, and `git log --oneline -3` shows the merge of `docs/readme-ai-settings`.

- [ ] **Step 7: Create the work branch**

Stop: ask James for OK to create `feat/portfolio-demo-readiness` from `dev`.
Run: `git checkout -b feat/portfolio-demo-readiness`

- [ ] **Step 8: Write `CLAUDE.md` with exactly this content**

```markdown
# Folio (brand-content-studio)

Folio is one of James Littlefield's portfolio apps: a retrieval-augmented studio that writes on-brand LinkedIn posts, image cards, and documents. A FastAPI server (`server/`: MongoDB through Motor, Chroma for vectors, OpenAI embeddings, Claude Sonnet 5.5 streamed over SSE) serves a React 19 + Vite client (`client/`). The public demo has no accounts: one click starts a private, temporary visitor session.

## Commands

- Local databases: `docker compose up -d` (loopback only)
- Dev servers: `npm run dev` (client on http://localhost:5173, API on http://localhost:8000)
- Seed the demo: `npm run seed`
- Server checks, in `server/`: `.venv/bin/ruff check app tests`, `.venv/bin/mypy app`, `.venv/bin/python -m pytest -q`
- Client checks, in `client/`: `npm run lint`, `npm run format`, `npm run build`, `npm test`
- Everything: `npm run ci`

## Rules

- Never commit, push, merge, or open a pull request without James's explicit OK, one action at a time.
- No paid runs (Anthropic, OpenAI, or anything else billed) without James's explicit OK for that run. Tests use the fakes in `server/tests/fakes.py` and empty API keys.
- American English everywhere. No em dashes anywhere: code, comments, copy, docs, commit and PR text.
- Before any push, run `/code-review` and `/security-review` and address the findings (docs/WORKFLOW.md, section 5).

## Plans

- Current work: `docs/superpowers/plans/2026-11-19-demo-sessions-and-deploy-readiness.md`
- Master plan for all four portfolio apps and AWS: `../portfolio-infra/PLAN.md`
- Design: `../portfolio-infra/docs/design/2026-11-18-portfolio-apps-aws-deployment-design.md`
```

- [ ] **Step 9: Commit**

Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.

```bash
git add CLAUDE.md docs/superpowers/plans/2026-11-19-demo-sessions-and-deploy-readiness.md
git commit -m "docs: plan the portfolio demo readiness work and add CLAUDE.md" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Upgrade uvicorn: trust the load balancer by CIDR, keep-alive 130, graceful stop

**Files:**
- Modify: `server/requirements.txt:7`
- Modify: `Dockerfile:37` (CMD)
- Modify: `server/app/config.py` (new setting, new `validate_serving_settings`)
- Modify: `server/app/main.py:123-129` (lifespan calls the validator)
- Modify: `server/.env.example`, `CHANGELOG.md`
- Create: `server/tests/test_proxy_headers.py`, `server/tests/test_dockerfile.py`
- Modify: `server/tests/test_settings_secrets.py`

**Interfaces:**
- Produces: `Settings.forwarded_allow_ips: str = "127.0.0.1"`; `def validate_serving_settings(s: Settings) -> None` in `app/config.py`, raising `ValueError` in production only. Called once in the lifespan before anything else. Task 9 adds checks to it. (Serving checks live here, not in the import-time validator, so the hourly cleanup job can run without the web app's settings.)

- [ ] **Step 1: Pick the version**

Run: `cd server && .venv/bin/pip index versions uvicorn`, then read the uvicorn release notes for the first release whose `forwarded_allow_ips` accepts IP networks (believed 0.31.0, "Improve ProxyHeadersMiddleware"). Pin the newest release at or above it. Starlette and FastAPI are unaffected (uvicorn is only the server).

- [ ] **Step 2: Write the failing tests** (`server/tests/test_proxy_headers.py`)

```python
from httpx import ASGITransport, AsyncClient
from slowapi.util import get_remote_address
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

ALB_PEER = ("10.0.3.7", 5555)

async def _key(trusted: str, peer: tuple[str, int], xff: str | None) -> str:
    async def echo(request):  # the exact key function the limiter uses (ratelimit.py:12)
        return PlainTextResponse(get_remote_address(request))
    app = ProxyHeadersMiddleware(Starlette(routes=[Route("/ip", echo)]), trusted_hosts=trusted)
    headers = {"x-forwarded-for": xff} if xff else {}
    async with AsyncClient(transport=ASGITransport(app=app, client=peer), base_url="http://t") as c:
        return (await c.get("/ip", headers=headers)).text

async def test_the_real_client_is_the_rightmost_untrusted_entry():
    assert await _key("10.0.0.0/16", ALB_PEER, "198.51.100.7, 203.0.113.9") == "203.0.113.9"

async def test_a_forged_leftmost_entry_does_not_change_the_rate_limit_key():
    honest = await _key("10.0.0.0/16", ALB_PEER, "203.0.113.9")
    forged = await _key("10.0.0.0/16", ALB_PEER, "1.2.3.4, 203.0.113.9")
    assert honest == forged == "203.0.113.9"

async def test_an_untrusted_peer_cannot_choose_its_address():
    assert await _key("10.0.0.0/16", ("192.0.2.50", 1), "203.0.113.9") == "192.0.2.50"

async def test_a_wildcard_would_trust_the_forged_entry():  # why validate_serving_settings refuses "*"
    assert await _key("*", ALB_PEER, "1.2.3.4, 203.0.113.9") == "1.2.3.4"
```

Add to `test_settings_secrets.py` (build settings with the file's `_settings` helper):

```python
@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "not-an-ip", ""])
def test_production_refuses_an_unsafe_forwarded_allow_ips(value):
    with pytest.raises(ValueError):
        validate_serving_settings(_settings(environment="production", forwarded_allow_ips=value))

def test_production_requires_forwarded_allow_ips_to_be_set():
    with pytest.raises(ValueError, match="FORWARDED_ALLOW_IPS"):
        validate_serving_settings(_settings(environment="production"))

def test_production_accepts_a_cidr_list():
    validate_serving_settings(_settings(environment="production", forwarded_allow_ips="10.0.0.0/16,127.0.0.1"))

def test_development_skips_the_serving_checks():
    validate_serving_settings(_settings(environment="development", forwarded_allow_ips="*"))
```

`server/tests/test_dockerfile.py` reads `Dockerfile` as text and asserts the `CMD` JSON array contains `"--proxy-headers"`, `"--timeout-keep-alive", "130"`, and `"--timeout-graceful-shutdown", "25"`, and contains neither `"--forwarded-allow-ips"` nor `"--workers"`.

- [ ] **Step 3: Run them to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_proxy_headers.py tests/test_dockerfile.py tests/test_settings_secrets.py -q`
Expected: the CIDR tests fail on uvicorn 0.24 (it compares the peer to `{"10.0.0.0/16"}` as a string, so the key stays `10.0.3.7`); the settings and Dockerfile tests fail on missing names and flags.

- [ ] **Step 4: Upgrade and implement**

- Pin `uvicorn[standard]==<chosen>` with a comment naming the CIDR support. Run `.venv/bin/pip install -r requirements-dev.txt` and confirm `grep -n "ip_network" .venv/lib/python3.12/site-packages/uvicorn/middleware/proxy_headers.py` finds the network parsing.
- `validate_serving_settings`: in production, require `"forwarded_allow_ips" in s.model_fields_set` (uvicorn reads the same `FORWARDED_ALLOW_IPS` variable itself, so the value is never passed on the command line); split on commas; each entry must parse with `ipaddress.ip_address` or `ipaddress.ip_network(strict=False)`; refuse `*` and any network with `prefixlen == 0`.
- Dockerfile `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--timeout-keep-alive", "130", "--timeout-graceful-shutdown", "25"]`, with a comment: keep-alive above the ALB's 120 s idle timeout; trusted proxies come from `FORWARDED_ALLOW_IPS`.
- `.env.example`: `# FORWARDED_ALLOW_IPS=127.0.0.1` with a comment (production: the VPC CIDR, never `*`).

- [ ] **Step 5: Run the tests, then the gate**

Run: the Step 3 command (expected PASS), then G-server.

- [ ] **Step 6: Commit**

CHANGELOG: `### Security: real client IPs behind a load balancer, and longer keep-alive`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `fix(server): trust the load balancer by CIDR and keep connections alive for 130 s`

---

### Task 3: One Claude client and one OpenAI client: timeouts, no SDK retries, fallbacks off

**Files:**
- Create: `server/app/services/ai_clients.py`, `server/tests/test_ai_clients.py`
- Modify: `server/app/services/claude_calls.py:34,48-56,74-79` (no fallback beta; per-request stream timeout)
- Modify: `server/app/services/ai_service.py:35-40`, `server/app/services/brand_extract_service.py:93-98` (use the shared client)
- Modify: `server/app/rag/embeddings.py:19-23` (shared OpenAI client)
- Modify: `server/app/config.py`, `server/app/main.py` (close clients at shutdown), `server/tests/conftest.py` (network guard), `server/tests/test_claude_calls.py`, `server/.env.example`, `CHANGELOG.md`

**Interfaces:**
- Produces: `get_anthropic() -> AsyncAnthropic` and `get_openai() -> OpenAI` (each `functools.lru_cache(maxsize=1)`), `async def close_ai_clients() -> None`, `def stream_timeout() -> httpx.Timeout`. Settings: `ai_request_timeout_s: float = 60.0`, `ai_stream_read_timeout_s: float = 30.0`, `ai_stream_deadline_s: float = 90.0`, `embedding_timeout_s: float = 10.0` (D4).
- `GenerationService` and `BrandExtractService` keep their zero-argument constructors (tests override them with `app.dependency_overrides`), but `self.client = get_anthropic()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_one_shared_anthropic_client_with_no_retries():
    client = ai_clients.get_anthropic()
    assert client is ai_clients.get_anthropic()
    assert client.max_retries == 0
    assert client.timeout.read == settings.ai_request_timeout_s and client.timeout.connect == 5.0

def test_the_services_use_the_shared_client():
    assert GenerationService().client is ai_clients.get_anthropic()
    assert BrandExtractService().client is ai_clients.get_anthropic()

def test_openai_client_has_no_retries_and_a_short_timeout():
    client = ai_clients.get_openai()
    assert client.max_retries == 0 and client.timeout == settings.embedding_timeout_s

def test_requests_carry_no_server_side_fallback():
    opts = claude_calls.request_options()
    assert "betas" not in opts and "fallbacks" not in opts
```

In `test_claude_calls.py`, update the request-shape test to assert no `betas`/`fallbacks`, and add `test_stream_sets_a_per_request_read_timeout` (the fake `stream(**kwargs)` records kwargs; `kwargs["timeout"].read == settings.ai_stream_read_timeout_s`).

Add an autouse fixture `_no_real_network` to `conftest.py`: monkeypatch `httpx.AsyncClient.send` and `httpx.Client.send` to raise `AssertionError(f"real network call in a test: {request.url.host}")` unless the client's transport is an `httpx.ASGITransport` or `httpx.MockTransport`. This is the suite's guard against paid calls.

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_ai_clients.py tests/test_claude_calls.py -q`
Expected: FAIL (`ai_clients` missing; `betas` present).

- [ ] **Step 3: Implement**

- `get_anthropic()`: `AsyncAnthropic(api_key=..., max_retries=0, timeout=httpx.Timeout(settings.ai_request_timeout_s, connect=5.0))`.
- `get_openai()`: `OpenAI(api_key=..., max_retries=0, timeout=settings.embedding_timeout_s)`.
- `stream_timeout()`: `httpx.Timeout(settings.ai_stream_read_timeout_s, connect=5.0)`, passed as `timeout=` on `client.beta.messages.stream(...)`. Keep the `client.beta.messages` namespace so the request shape is otherwise unchanged; drop `FALLBACK_BETA`, `betas`, and `fallbacks`, and update the module docstring (DECISIONS #40 is amended in Task 17).
- `close_ai_clients()`: close whichever cached clients exist (`cache_info().currsize`), then `cache_clear()`. The lifespan calls it after `close_mongo_connection()`.
- `.env.example`: the four timeout settings, commented, with defaults.

- [ ] **Step 4: Run the tests, then the gate**

Run: Step 2 command (expected PASS), then G-server.

- [ ] **Step 5: Commit**

CHANGELOG: `### Changed: one shared Claude client, explicit timeouts, no SDK retries, no fallback`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `fix(server): one Claude client and one OpenAI client, no SDK retries, fallbacks off`

---

### Task 4: The dollar ledger: pricing, pacing, reserve and settle, sweeper, public status flag

**Files:**
- Create: `server/app/services/ai_pricing.py`, `server/app/services/ai_ledger.py`, `server/app/services/ai_meter.py`, `server/app/routes/status.py`, `server/app/jobs/__init__.py`, `server/app/jobs/cleanup.py`
- Create: `server/tests/test_ai_pricing.py`, `server/tests/test_ai_ledger.py`, `server/tests/test_ai_meter.py`, `server/tests/test_status.py`, `server/tests/test_cleanup_job.py`
- Modify: `server/app/utils/errors.py` (code field, copy, two errors), `server/app/main.py:150-159` (handler sends `code`; include the status router at `/api/status`), `server/app/config.py`, `server/app/database.py` (ledger indexes), `server/tests/conftest.py` (collections list becomes a `TEST_COLLECTIONS` constant including the three ledger collections), `server/.env.example`, `CHANGELOG.md`

**Interfaces:**
- `errors.py`: `UserFacingError.code: str | None = None` (class attribute, overridable per instance); `class BudgetRefusal(UserFacingError)` with `status_code = 429`, `__init__(self, reason: Literal["off", "today", "month", "visitor"])`, code `visitor_allowance` for `visitor` else `live_ai_paused`, message the matching copy; `class LiveAIUnavailable(UserFacingError)` with `status_code = 503`, code `live_ai_unavailable`, `__init__(self, *, log_detail: str)`. The app handler returns `{"detail": message, "code": code}` (`code` only when set).
- `ai_pricing.py`: `def usd_to_micros(usd: Decimal) -> int`; `def estimate_tokens(text: str) -> int`; `IMAGE_TOKEN_BOUND = 5_000`; `SCHEMA_OVERHEAD_TOKENS = 500`; `def claude_reservation_micros(model: str, *, input_tokens: int, max_tokens: int) -> int`; `def claude_cost_micros(model: str, *, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> int` (an unknown model is priced at the dearest row, with a warning); `def embedding_reservation_micros(model: str, texts: Sequence[str]) -> int` (at least 1); `def embedding_cost_micros(model: str, tokens: int) -> int`; `def is_priced(model: str) -> bool`. Amounts round up (`ROUND_CEILING`).
- `ai_ledger.py`:
  - `@dataclass(frozen=True) class LineRequest: provider: Literal["anthropic", "openai"]; model: str; purpose: str; reserved_micros: int`
  - `@dataclass(frozen=True) class ReservedLine: id: ObjectId; day: str; visitor_id: str | None; provider: str; model: str; purpose: str; reserved_micros: int`
  - `@dataclass(frozen=True) class BudgetSnapshot: allowance_today: int; spent_today: int; left_this_month: int`
  - `def allowance_micros(*, budget: int, spent_before_today: int, days_left: int, multiplier: Decimal, floor: int) -> int`
  - `async def reserve(db, requests: Sequence[LineRequest], *, visitor_id: str | None, now: datetime | None = None) -> list[ReservedLine]` (raises `BudgetRefusal`)
  - `async def settle(db, line: ReservedLine, *, actual_micros: int, outcome: str, now: datetime | None = None) -> bool` (False if already settled)
  - `async def sweep_stale(db, *, now: datetime | None = None) -> int`; `STALE_AFTER = timedelta(minutes=10)`
  - `async def prune_closed(db, *, now: datetime | None = None, older_than: timedelta = timedelta(days=35)) -> int`
  - `async def budget_snapshot(db, *, now: datetime | None = None) -> BudgetSnapshot`
  - `async def delete_visitor(db, visitor_id: str) -> None` (Task 10's cleanup uses it)
- `ai_meter.py`:
  - `class MeteredLine` (`__init__(self, db, reserved: ReservedLine)`; `started: bool`; `settled: bool`; `def mark_started(self) -> None`; `async def settle_usage(self, *, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> None`; `async def settle_tokens(self, tokens: int) -> None` (embeddings); `async def settle_unbilled(self, outcome: str) -> None`; `async def settle_reserved(self, outcome: str) -> None`). Every settle is a no-op once settled.
  - `class MeteredAction` (`lines: list[MeteredLine]`; `async def finalize(self) -> None`; async context manager calling `finalize` on exit). `finalize` runs under `anyio.CancelScope(shield=True)`: an unsettled line that started settles at its reserved amount (`outcome="canceled_or_unknown"`), one that never started settles at 0 (`outcome="not_attempted"`).
  - `async def reserve_action(db, requests: Sequence[LineRequest], *, visitor_id: str | None) -> MeteredAction`
  - `def claude_line(purpose: str, *, system: str, content: str | list[dict[str, Any]], max_tokens: int, schema: dict[str, Any] | None = None, extra_input_tokens: int = 0) -> LineRequest` (model `settings.ai_model`; input = estimate of system and every text part, plus `IMAGE_TOKEN_BOUND` per image part, plus `estimate_tokens(json.dumps(schema)) + SCHEMA_OVERHEAD_TOKENS` when a schema is given, plus `extra_input_tokens`)
  - `def embedding_line(purpose: str, texts: Sequence[str]) -> LineRequest` (model `settings.embedding_model`)
- `status.py`: `GET /api/status` (no auth) returns `StatusResponse(live_ai_available: bool, live_ai_reason: Literal["available", "off", "paused"])`, cached in process for 30 s, header `Cache-Control: public, max-age=30`. Available when the budget is above 0 and `allowance_today - spent_today >= STATUS_MIN_ROOM_MICROS` (60_000, about one text post).
- `cleanup.py`: `async def run_cleanup(db, *, now: datetime | None = None) -> dict[str, int]` (keys `swept`, `pruned`); `def main() -> None` (own Motor client, `maxPoolSize=2`; logs `cleanup: swept=N pruned=N`; exits 1 on any exception so the scheduled-task alarm fires). Run as `python -m app.jobs.cleanup`.
- Settings: `ai_monthly_budget_usd: Decimal = Decimal("10")`, `ai_pacing_multiplier: Decimal = Decimal("3")`, `ai_daily_floor_usd: Decimal = Decimal("0.50")`, `ai_visitor_budget_usd: Decimal = Decimal("0.15")`.
- Documents: `ai_spend_days {_id: "YYYY-MM-DD", month: "YYYY-MM", total_micros}` (settled + open, never deleted); `ai_spend_calls {_id, day, month, visitor_id, provider, model, purpose, reserved_micros, actual_micros|null, status: "open"|"settled"|"swept", outcome, created_at, settled_at}`; `ai_spend_visitors {_id: visitor_id, total_micros}`. Indexes: `ai_spend_calls (status, created_at)`, `ai_spend_days month`.

- [ ] **Step 1: Write the failing tests**

`test_ai_pricing.py`:
```python
def test_sonnet_reservation_is_input_at_2_and_output_at_10_micros_per_token():
    assert claude_reservation_micros("claude-sonnet-5-5", input_tokens=8_000, max_tokens=4_000) == 56_000
def test_sonnet_cost_from_usage():
    assert claude_cost_micros("claude-sonnet-5-5", input_tokens=1_000, output_tokens=200) == 4_000
def test_an_unknown_model_is_priced_at_the_dearest_row():
    assert claude_cost_micros("claude-unknown", input_tokens=1_000, output_tokens=0) == 5_000
def test_estimate_is_two_bytes_a_token(): assert estimate_tokens("x" * 2_001) == 1_001
def test_embedding_costs():
    assert embedding_reservation_micros("text-embedding-3-small", ["x" * 2_000]) == 20
    assert embedding_cost_micros("text-embedding-3-small", 6_000) == 120
```

`test_ai_ledger.py` (fixed clock `NOV19 = datetime(2026, 11, 19, 15, tzinfo=UTC)`; November has 12 days left including the 19th; `_req(m)` builds a `LineRequest("anthropic", "claude-sonnet-5-5", "test", m)`):
```python
@pytest.mark.parametrize("spent_before, days_left, expected", [
    (0, 30, 1_000_000), (4_000_000, 12, 1_500_000), (9_800_000, 12, 200_000), (8_000_000, 20, 500_000)])
def test_allowance_follows_the_pacing_formula(spent_before, days_left, expected):
    assert allowance_micros(budget=10_000_000, spent_before_today=spent_before, days_left=days_left,
                            multiplier=Decimal(3), floor=500_000) == expected

async def test_reserve_admits_up_to_todays_allowance_then_refuses(test_db):  # 3 x 10 / 12 = $2.50
    await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    with pytest.raises(BudgetRefusal) as refused:
        await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    assert refused.value.code == "live_ai_paused"
    assert (await test_db.ai_spend_days.find_one({"_id": "2026-11-19"}))["total_micros"] == 2_000_000

async def test_spend_before_today_lowers_todays_allowance(test_db): ...  # day docs Nov 1-18 total 4_000_000: 1_400_000 admitted, then 200_000 refused
async def test_a_new_utc_month_starts_with_the_full_budget(test_db): ...  # Nov total 9_900_000; on Dec 1 a 900_000 reservation is admitted (3 x 10 / 31)
async def test_the_month_is_never_exceeded(test_db): ...  # 9_950_000 before today: allowance 50_000, so 60_000 is refused
async def test_the_visitor_allowance_refuses_past_15_cents(test_db): ...  # visitor "s1": 100_000 admitted, 60_000 refused with code "visitor_allowance"; day total stays 100_000
async def test_concurrent_reservations_cannot_overshoot_the_visitor_allowance(test_db):
    results = await asyncio.gather(*(reserve(test_db, [_req(40_000)], visitor_id="s2", now=NOV19) for _ in range(10)), return_exceptions=True)
    assert sum(not isinstance(r, BudgetRefusal) for r in results) == 3
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s2"}))["total_micros"] == 120_000
    assert (await test_db.ai_spend_days.find_one({"_id": "2026-11-19"}))["total_micros"] == 120_000
async def test_concurrent_reservations_cannot_overshoot_the_day(test_db): ...  # 10 x 400_000 against $2.50: exactly 6 admitted
async def test_settle_moves_every_total_to_the_actual_cost(test_db): ...  # reserve 56_000 for "s3", settle 4_000: day 4_000, visitor 4_000, call doc settled
async def test_settle_is_idempotent(test_db): ...  # second settle returns False, totals unchanged
async def test_settle_after_midnight_goes_to_the_reservation_day(test_db): ...  # reserve 23:59:50 Nov 19, settle 00:00:30 Nov 20: Nov 19 doc changes, no Nov 20 doc
async def test_the_sweeper_charges_reservations_older_than_ten_minutes(test_db): ...  # one at t, one at t+9 min; sweep at t+11 min returns 1; status "swept"; totals unchanged
async def test_a_zero_budget_refuses_without_touching_the_database(monkeypatch): ...  # settings budget 0, a db object whose attribute access fails the test; reason "off"
```

`test_ai_meter.py`: `test_finalize_releases_lines_that_never_started` (actual 0, outcome `not_attempted`); `test_finalize_keeps_a_started_unsettled_line_at_its_reservation`; `test_finalize_still_settles_when_the_task_is_canceled` (cancel an `anyio` scope around `async with action:` after `mark_started`; afterwards the call doc is settled at the reserved amount); `test_claude_line_counts_text_images_schema_and_extra` (one 2,000-byte text, one image, a schema, `extra_input_tokens=2_000`: input = 1,000 + 5,000 + schema estimate + 500 + 2,000).

`test_status.py`: budget 0 gives `{"live_ai_available": false, "live_ai_reason": "off"}`; room under 60_000 gives `"paused"`; otherwise `"available"`; a second call within 30 s doesn't read the database; `Cache-Control: public, max-age=30`.

`test_cleanup_job.py`: `run_cleanup` sweeps one stale reservation and prunes one settled call older than 35 days, returning `{"swept": 1, "pruned": 1}`.

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_ai_pricing.py tests/test_ai_ledger.py tests/test_ai_meter.py tests/test_status.py tests/test_cleanup_job.py -q`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement `reserve` with exactly this algorithm** (atomicity without a lock; the shapes follow `usage_service.consume_demo_ai_action`)

```text
budget = usd_to_micros(settings.ai_monthly_budget_usd); if budget == 0: raise BudgetRefusal("off")   # no database access
amount = sum(r.reserved_micros for r in requests); day = now "%Y-%m-%d"; month = now "%Y-%m"
spent_before = sum(total_micros of ai_spend_days where month == month and _id < day)
left = max(budget - spent_before, 0); days_left = monthrange(year, month)[1] - now.day + 1
allowance = allowance_micros(budget, spent_before, days_left, multiplier, floor)
if visitor_id: cap = usd_to_micros(settings.ai_visitor_budget_usd)
    # Shared rule (portfolio-infra/PLAN.md, 2026-11-19): admit while the visitor has room left,
    # counted at settled + open spend; one call may overshoot. The day check below still reserves the worst case.
    conditional_inc(ai_spend_visitors, {_id: visitor_id, total_micros: {$lt: cap}}, amount)
    on no match: raise BudgetRefusal("visitor")
if amount > allowance or not conditional_inc(ai_spend_days, {_id: day, total_micros: {$lte: allowance - amount}}, amount, set_on_insert={month}):
    if visitor_id: $inc visitor by -amount                     # compensate
    raise BudgetRefusal("month" if allowance >= left else "today")
insert_many one ai_spend_calls doc per request (status "open", created_at now)
on any exception here: compensate both counters, then re-raise
conditional_inc = update_one(filter, {$inc, $setOnInsert}, upsert=True); on DuplicateKeyError retry
update_one(filter, {$inc}) without upsert and return modified_count == 1
```

`settle`: `find_one_and_update({_id: line.id, status: "open"}, {$set: {status: "settled", actual_micros, outcome, settled_at}})`; when it matched and `delta = actual - reserved != 0`, `$inc total_micros` by `delta` on the reservation's day doc and on the visitor doc (a missing visitor doc is fine: its session was cleaned up). `sweep_stale`: `update_many({status: "open", created_at: {$lt: now - STALE_AFTER}}, {$set: {status: "swept", outcome: "swept", settled_at: now}})`; the totals already hold the reserved amounts. Wire `ensure_ledger_indexes` into `ensure_indexes`.

- [ ] **Step 4: Run the tests, then the gate**

Run: Step 2 command (expected PASS), then G-server.

- [ ] **Step 5: Commit**

CHANGELOG: `### Added: an AI dollar ledger with daily pacing and a public status flag` (not wired to calls yet).
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(server): add the AI dollar ledger with daily pacing and a public status flag`

---

### Task 5: Every Claude call through the ledger; reserve before streaming; friendly refusals

**Files:**
- Create: `server/app/services/ai_failures.py`, `server/tests/test_ai_failures.py`, `server/tests/test_ai_routes_budget.py`
- Modify: `server/app/services/claude_calls.py` (whole file), `server/app/services/ai_service.py`, `server/app/services/brand_extract_service.py`
- Modify: `server/app/routes/generate.py:48-227`, `server/app/routes/documents.py:50-144`, `server/app/routes/templates.py:133-213`, `server/app/routes/workspaces.py:137-174`
- Modify: `server/app/utils/dependencies.py:87-103` (remove the quota; add `ledger_visitor_id`), `server/app/main.py:147` (friendly rate-limit handler), `server/app/config.py:39-43` (remove `demo_daily_generation_limit`), `server/app/database.py:48-50` (stop creating the `usage` TTL index), `server/app/limits.py:9` (docstring), `server/.env.example:24-25`
- Delete: `server/app/services/usage_service.py`, `server/tests/test_demo_ai_quota.py`
- Modify tests: `fakes.py`, `test_claude_calls.py`, `test_generate_route.py`, `test_documents.py`, `test_templates.py`, `test_brand_extract.py`, `test_exemplars.py`, `test_rate_limit.py`; `CHANGELOG.md`

**Interfaces:**
- Consumes: Task 4's `reserve_action`, `claude_line`, `MeteredLine`, `BudgetRefusal`, `LiveAIUnavailable`; Task 3's `get_anthropic`, `stream_timeout`.
- Produces:
  - `ai_failures.py`: `class Billing(Enum): UNBILLED, BILLED_OR_UNKNOWN`; `def classify_anthropic_error(exc: BaseException, *, output_started: bool) -> Billing`; `def is_usage_limit_message(message: str) -> bool` (regex `^You have reached your specified (workspace |organization )?API usage limits`, plus the 400 "credit balance is too low" text, case-insensitive); `def is_provider_outage(exc: BaseException) -> bool` (true for 401, 402, 403, any 429, 5xx, 529, usage-limit or credit 400s, connection errors, timeouts).
  - `claude_calls.stream_text(client, *, system: str, user: str, max_tokens: int, line: MeteredLine) -> AsyncGenerator[str, None]`; `claude_calls.structured_call(client, *, system: str, content: str | list[dict[str, Any]], tool: dict[str, Any], max_tokens: int, line: MeteredLine) -> dict[str, Any]`.
  - Every `GenerationService` method and `BrandExtractService.propose` / `propose_exemplar_note` take a keyword-only `line: MeteredLine`.
  - `dependencies.ledger_visitor_id(user: UserInDB) -> str | None` returns `None` here; Task 9 returns the session ID for demo users.
  - `NO_CONTEXT_COPY = "No brand context could be retrieved for this brief."` (the existing text, now a 409).
  - `FakeGenerationService` methods take `line`, call `line.mark_started()`, and settle with `FAKE_INPUT_TOKENS = 1_000`, `FAKE_OUTPUT_TOKENS = 200` (4,000 micros a call).

- [ ] **Step 1: Write the failing tests**

`test_ai_failures.py` (build SDK errors as `anthropic.AuthenticationError("x", response=httpx.Response(401, request=REQ), body={...})`):
```python
@pytest.mark.parametrize("exc", [auth_401(), permission_403(), status_402(),
    bad_request_400("You have reached your specified workspace API usage limits. ..."),
    bad_request_400("You have reached your specified organization API usage limits. ..."),
    rate_limit_429(body={"type": "error", "error": {"type": "rate_limit_error", "message": "enforced_spend_limit_reached"}})])
def test_known_unbilled_failures(exc):
    assert classify_anthropic_error(exc, output_started=False) is Billing.UNBILLED
def test_overloaded_is_unbilled_only_before_output():
    assert classify_anthropic_error(overloaded_529(), output_started=False) is Billing.UNBILLED
    assert classify_anthropic_error(overloaded_529(), output_started=True) is Billing.BILLED_OR_UNKNOWN
@pytest.mark.parametrize("exc", [timeout_error(), connection_error(), bad_request_400("invalid model"), rate_limit_429(body={})])
def test_everything_else_keeps_the_reservation(exc):
    assert classify_anthropic_error(exc, output_started=False) is Billing.BILLED_OR_UNKNOWN
```
(Shared rule update 2026-11-19 in `portfolio-infra/PLAN.md`: any 429 before output, plain rate limit included, is UNBILLED, because the request is rejected before any work is done. Add a plain 429 with no `error_code` to the `test_known_unbilled_failures` cases.)

`test_claude_calls.py` additions, using a `RecordingLine` test double with `started`, `settled`, and the arguments of the last settle:
- `test_stream_settles_usage_before_a_decline_is_raised` and `test_stream_settles_usage_before_a_token_cap_error`;
- `test_structured_call_settles_before_decline_cap_or_bad_json` (parametrized over the three);
- `test_unbilled_errors_settle_to_zero_and_raise_live_ai_unavailable` (parametrized as above);
- `test_timeouts_and_connection_errors_keep_the_reservation` (settled at reserved, `LiveAIUnavailable`);
- `test_other_bad_requests_keep_the_reservation_and_reraise_the_original`;
- `test_a_canceled_stream_settles_at_the_reserved_amount_and_closes_the_sdk_stream` (cancel while the fake stream waits on an `anyio.Event`; the fake records that its `__aexit__` ran);
- `test_the_stream_deadline_keeps_the_reservation` (monkeypatch `settings.ai_stream_deadline_s = 0`).

`test_ai_routes_budget.py` (replaces `test_demo_ai_quota.py`; owner user, ready workspace, `FakeVectorStore`, `FakeGenerationService`, real `test_db`):
```python
PAID = [("/generate/text", TEXT_BODY), ("/generate/card", CARD_BODY), ("/generate/post", POST_BODY),
        ("/generate/document", DOC_BODY), (f"/templates/{TPL}/ai-fill", FILL_BODY)]  # plus fill-from-document as a file upload
@pytest.mark.parametrize("path, body", PAID)
async def test_a_zero_budget_refuses_every_paid_route_before_any_call(client, monkeypatch, path, body):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    resp = await client.post(WS + path, json=body)
    assert resp.status_code == 429
    assert resp.json() == {"detail": LIVE_AI_PAUSED_COPY, "code": "live_ai_paused"}
    assert client.fake_gen.calls == [] and client.fake_gen.card_field_calls == []
async def test_text_generation_settles_its_one_call(client, test_db): ...  # one ai_spend_calls doc, settled, actual 4_000
async def test_card_generation_settles_both_calls(client, test_db): ...  # two docs, both actual 4_000
async def test_an_empty_copy_releases_the_unused_fields_call(client, test_db): ...  # fake copy "" -> fields doc actual 0, outcome "not_attempted"
async def test_the_fields_call_reserves_room_for_the_whole_copy(client, test_db): ...  # fields reserved = 2 x (est(system) + est(user with empty copy) + schema est + 500 + 2_000) + 10 x 4_000
async def test_no_retrieved_context_is_a_409_before_any_reservation(client, test_db): ...
async def test_brand_extract_is_closed_to_the_demo(client): ...  # demo user: 403, extractor never called
async def test_brand_extract_and_exemplars_reserve_for_owners(client, test_db): ...  # one settled doc each, input includes IMAGE_TOKEN_BOUND
```
`test_rate_limit.py`: the 429 body is `{"detail": RATE_LIMITED_COPY, "code": "rate_limited"}` (today slowapi answers `{"error": "Rate limit exceeded: ..."}`, extension.py:81-83, which the client can't show).

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_ai_failures.py tests/test_claude_calls.py tests/test_ai_routes_budget.py tests/test_rate_limit.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `stream_text` with this structure** (`structured_call` is the same without the stream: settle right after `create` returns, then the decline, cap, and JSON checks)

```python
line.mark_started()
output_started = False
deadline = time.monotonic() + settings.ai_stream_deadline_s
manager = client.beta.messages.stream(max_tokens=max_tokens, system=system,
    messages=[{"role": "user", "content": user}], timeout=stream_timeout(), **request_options())
try:
    stream = await manager.__aenter__()
    try:
        async for text in stream.text_stream:
            output_started = True
            yield text
            if time.monotonic() > deadline:
                raise StreamDeadlineExceeded
        final = await stream.get_final_message()
    finally:  # shielded and bounded, so a cancel can't leave the upstream call generating
        with anyio.move_on_after(5, shield=True):
            await manager.__aexit__(None, None, None)
    await line.settle_usage(model=final.model, **_usage_tokens(final.usage))  # billed: settle first
    _raise_if_declined(final)
    if final.stop_reason == "max_tokens":
        raise RuntimeError(f"Streamed output hit the {max_tokens}-token cap.")
except anthropic.APIError as exc:
    if classify_anthropic_error(exc, output_started=output_started) is Billing.UNBILLED:
        await line.settle_unbilled(type(exc).__name__)
    if is_provider_outage(exc):
        raise LiveAIUnavailable(log_detail=f"Claude call failed: {type(exc).__name__}") from exc
    raise
except StreamDeadlineExceeded as exc:
    raise LiveAIUnavailable(log_detail="Claude stream passed its deadline") from exc
finally:
    if not line.settled:  # canceled, timed out, or unknown: keep the whole reservation
        with anyio.CancelScope(shield=True):
            await line.settle_reserved("canceled_or_unknown")
```
`_usage_tokens` reads `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (None as 0). If `usage.iterations` is present (a fallback ran despite the setting), price each iteration by its own model and sum, as the master plan's ledger rule says.

- [ ] **Step 4: Rewire the routes**

Each SSE route (text, card, post, document) does, in order, before returning `sse_response`: `ensure_ready_corpus`; build the brand context; `retrieve(...)` (unchanged until Task 6); `if not result.chunks: raise HTTPException(409, NO_CONTEXT_COPY)`; build every prompt; `action = await reserve_action(db, [...lines], visitor_id=ledger_visitor_id(current_user))`. The second line of a two-call action is estimated with the second prompt built from an empty copy, caption, or draft, plus `extra_input_tokens` equal to the first call's `max_tokens`. Inside `produce()`, pass `line=action.lines[i]` to each call and wrap the body in `try: ... finally: await action.finalize()`. Add `current_user: UserInDB = Depends(get_current_user)` to each route (FastAPI resolves it once per request).

Non-streaming routes (template AI fill, fill from a document, brand extract, exemplars) build the prompt, then `async with await reserve_action(...) as action:` around the call. Brand extract also gets `Depends(require_not_demo)` (the UI already hides it for the demo, BrandIdentityEditor.tsx:12-17).

Replace the slowapi handler with `_rate_limited_handler` returning `{"detail": RATE_LIMITED_COPY, "code": "rate_limited"}` with status 429 and the limiter's headers (`request.app.state.limiter._inject_headers(...)`). Remove `enforce_demo_ai_quota`, `usage_service.py`, `demo_daily_generation_limit`, and the `usage` index creation (keep the old-index drop at database.py:52-53).

- [ ] **Step 5: Run the tests, then the gate**

Run: Step 2 command plus `tests/test_generate_route.py tests/test_documents.py tests/test_templates.py tests/test_brand_extract.py tests/test_exemplars.py` (expected PASS), then G-server.

- [ ] **Step 6: Commit**

CHANGELOG: `### Changed: every Claude call is reserved before it runs; refusals read plainly` (supersedes the daily count from DECISIONS #35).
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(server): reserve every Claude call before it runs and refuse in plain words`

---

### Task 6: Every embedding call through the ledger

**Files:**
- Modify: `server/app/rag/embeddings.py`, `server/app/rag/vector_store.py:31-44` (protocol), `server/app/rag/chroma_store.py:29-71`, `server/app/rag/qdrant_store.py` (signatures only; deleted in Task 8), `server/app/services/retrieval_service.py:62-90`, `server/app/services/ingestion_service.py:67-120`, `server/seed/seed_demo.py:109-168`
- Modify: the four SSE routes (reserve the retrieval embedding), `server/tests/fakes.py` (`FakeEmbedder`, protocol signatures), `server/tests/conftest.py` (autouse `FakeEmbedder`)
- Create: `server/tests/test_embeddings_metered.py`
- Modify tests: `test_retrieval.py`, `test_ingestion.py`, `test_ingestion_safety.py`, `test_reingest_and_demo.py`, `test_generate_route.py`, `test_ai_routes_budget.py`; `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `Embedder` protocol: `def embed_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int]` (vectors and the response's `usage.total_tokens`). `OpenAIEmbedder` uses `get_openai()`.
  - `async def embed_metered(texts: list[str], *, line: MeteredLine) -> list[list[float]]` in `app/rag/embeddings.py`: marks started, runs `embed_with_usage` in `asyncio.to_thread`, settles with `settle_tokens`. OpenAI `AuthenticationError`, `PermissionDeniedError`, `BadRequestError`, and `RateLimitError` (including `insufficient_quota` and `credit_balance_exhausted`) settle to 0; timeouts and connection errors keep the reservation. Every `openai.APIError` becomes `LiveAIUnavailable` (today it surfaces as "Something went wrong", utils/sse.py:49-50).
  - `VectorStore.upsert_chunks(workspace_id: str, chunks: list[Chunk], embeddings: list[list[float]]) -> int`; `VectorStore.query(workspace_id: str, query: str, query_embedding: list[float], k: int = 6) -> list[RetrievedChunk]` (stores no longer embed; `FakeVectorStore` keeps ranking by the text).
  - `retrieval_service.retrieve(store, namespace: str, query: str, k: int = 6, *, line: MeteredLine) -> RetrievalResult` (the embedding overlaps the pinned fetch, as today).
  - `INGEST_PAUSED_COPY = "Ingestion is paused because today's AI budget is used up. Retry later."`
  - `FakeEmbedder.embed_with_usage` returns one deterministic 8-float vector per text and `sum(len(t) // 4 for t in texts)` tokens; an autouse conftest fixture installs it for every test.

- [ ] **Step 1: Write the failing tests** (`test_embeddings_metered.py`)

```python
async def test_embedding_settles_from_the_reported_tokens(test_db): ...  # FakeEmbedder reports 1_000 tokens: actual 20 micros
@pytest.mark.parametrize("exc", [openai_429("insufficient_quota"), openai_429("credit_balance_exhausted"), openai_401()])
async def test_openai_limit_and_auth_errors_settle_to_zero_and_read_plainly(test_db, exc): ...  # actual 0; LiveAIUnavailable
async def test_openai_timeouts_keep_the_reservation(test_db): ...
async def test_card_generation_meters_the_query_embedding(client, test_db): ...  # three settled docs: retrieval, card_copy, card_fields
async def test_a_zero_budget_spends_nothing_on_retrieval(client, test_db, monkeypatch): ...  # 429, embedder never called
async def test_ingestion_is_refused_cleanly_when_the_budget_is_used(test_db, monkeypatch): ...  # asset status "error", message INGEST_PAUSED_COPY, embedder never called
```

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_embeddings_metered.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In each SSE route, before `retrieve`: `retrieval = await reserve_action(db, [embedding_line("retrieval", [payload.brief])], visitor_id=...)`, then `async with retrieval: result = await retrieve(..., line=retrieval.lines[0])`. Then the Task 5 reservation for the model calls (D3: two reservations, both before the response). Ingestion reserves `embedding_line("ingest", texts)` with `visitor_id=None`; a `BudgetRefusal` or `LiveAIUnavailable` marks the asset `error` with `INGEST_PAUSED_COPY` or `LIVE_AI_UNAVAILABLE_COPY`. The seed's corpus step reserves with `visitor_id=None` (it moves to the free fixture in Task 8).

- [ ] **Step 4: Run the tests, then the gate**

Run: `cd server && .venv/bin/python -m pytest tests/test_embeddings_metered.py tests/test_retrieval.py tests/test_ingestion.py tests/test_ingestion_safety.py tests/test_reingest_and_demo.py tests/test_generate_route.py -q` (expected PASS), then G-server.

- [ ] **Step 5: Commit**

CHANGELOG: `### Changed: embeddings go through the AI ledger too`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(rag): meter every embedding call through the ledger`

---

### Task 7: SSE heartbeats and disconnect-safe settling

**Files:**
- Modify: `server/app/utils/sse.py` (whole file)
- Modify: `server/tests/test_sse.py`; create `server/tests/test_stream_disconnect.py`
- Modify: `client/src/lib/sse.test.ts`; `CHANGELOG.md`

**Interfaces:**
- Produces: `HEARTBEAT = ": keep-alive\n\n"`; `HEARTBEAT_INTERVAL_S = 10.0`; `sse_response(events: AsyncGenerator[dict, None], *, context: str, heartbeat_s: float = HEARTBEAT_INTERVAL_S) -> StreamingResponse`, returning a `_ClosingStreamingResponse`.
- Why both pieces: Starlette cancels the generator on disconnect only for ASGI spec versions below 2.4 (responses.py:272-280; uvicorn 0.24 reports 2.3, h11_impl.py:212). From 2.4 on, `send` raises `OSError` instead (responses.py:267-271) and the generator would wait for garbage collection before its `finally` (and the settle) runs. The subclass closes it at once in both cases.

- [ ] **Step 1: Write the failing tests**

`test_sse.py`:
```python
async def test_a_heartbeat_comment_is_sent_while_the_model_is_silent():
    async def slow():
        await asyncio.sleep(0.25)
        yield {"text": "hi"}
    body = await _collect(sse_response(slow(), context="t", heartbeat_s=0.05))
    assert body.count(": keep-alive\n\n") >= 3
    assert body.endswith('data: {"text": "hi"}\n\ndata: [DONE]\n\n')
async def test_no_heartbeat_when_frames_keep_coming(): ...
```
`test_stream_disconnect.py` (drive the real app with a raw ASGI call to `/generate/text`; a `BlockingGenerationService` yields one delta, then waits on an `asyncio.Event` that never fires):
```python
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_a_disconnect_settles_the_reservation_at_the_reserved_amount(test_db, spec_version): ...
    # 2.3: receive() returns {"type": "http.disconnect"} after the first body message is sent.
    # 2.4: send() raises OSError on the second body message.
    # After app(scope, receive, send) returns: the call doc is settled, actual == reserved,
    # outcome "canceled_or_unknown"; the retrieval doc is settled from usage; the fake recorded aclose.
```
`client/src/lib/sse.test.ts`: `ignores heartbeat comments and keeps the stream alive` (frames `: keep-alive` between text frames; with fake timers past 30 s of heartbeats only, no "stalled" error).

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_sse.py tests/test_stream_disconnect.py -q` and `cd client && npx vitest run src/lib/sse.test.ts`
Expected: server FAIL; the client test likely passes already (the parser drops non-JSON frames, sse.ts:126-137); keep it as a guard.

- [ ] **Step 3: Implement with exactly this algorithm**

```python
class _ClosingStreamingResponse(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:  # run the generators' finally blocks (settles) now, whatever ended the stream
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()

async def _with_heartbeats(frames: AsyncIterator[str], interval_s: float) -> AsyncIterator[str]:
    it = frames.__aiter__()
    pending: asyncio.Task[str] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval_s)  # never cancels pending
            if not done:
                yield HEARTBEAT
                continue
            task, pending = pending, None
            try:
                frame = task.result()
            except StopAsyncIteration:
                return
            yield frame
    finally:
        with anyio.CancelScope(shield=True):
            if pending is not None and not pending.done():
                pending.cancel()  # one native cancel; the inner finally settles (shielded)
                await asyncio.wait({pending})
            with contextlib.suppress(Exception):
                await it.aclose()
```
`sse_response` keeps its framing, its `UserFacingError` and redacted-error frames (now `{"error": message, "code": code}` when the error has a code), and the terminal `[DONE]`, and wraps the framed generator in `_with_heartbeats`.

- [ ] **Step 4: Run the tests, then the gates**

Run: Step 2 commands (expected PASS), then G-server and G-client.

- [ ] **Step 5: Commit**

CHANGELOG: `### Fixed: streams send heartbeats and settle their cost when the visitor leaves`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `fix(server): heartbeat SSE streams and settle on disconnect`

---

### Task 8: Chroma in-process (PersistentClient), no Chroma server

D2 is decided (James accepted it on 2026-11-19), so no stop is needed here. The export in Step 2 is free. Step 3 is a paid run only if the export is incomplete, and then it stops for James's OK with the expected cost.

**Files:**
- Modify: `server/app/rag/chroma_store.py:1-27`, `server/app/rag/vector_store.py` (add `count`; chroma only), `server/app/config.py:67-72` (`chroma_path`; remove `chroma_host`, `chroma_port`, `vector_store_backend` stays with one value, `qdrant_*` removed)
- Delete: `server/app/rag/qdrant_store.py`; remove `qdrant-client` from `server/requirements.txt:32` and the qdrant block from `server/mypy.ini`
- Modify: `server/requirements.txt:24-31` (chromadb comment), `server/seed/seed_demo.py` (fixture helpers and fixture-based corpus), `docker-compose.yml:14-27` (drop the `chroma` service and volume), `.dockerignore` (add `server/chroma/`), `.github/workflows/ci.yml:63-122,127-179,217-236`, `server/tests/conftest.py` (temporary Chroma dir), `server/tests/fakes.py` (`count`), `server/.env.example:38-43`
- Create: `server/seed/build_embeddings_fixture.py`, `server/seed/fixtures/verdure_embeddings.json`, `server/tests/test_chroma_store.py`, `server/tests/test_seed_embeddings_fixture.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `Settings.chroma_path: str = "./chroma"`; `VectorStore.count(workspace_id: str) -> int`; in `seed/seed_demo.py`: `EMBEDDINGS_FIXTURE: Path`, `def chunk_key(text: str) -> str` (sha256 hex of the UTF-8 text), `def corpus_chunks(namespace: str, asset_ids: Mapping[str, str]) -> list[Chunk]` (the seed's chunks for the five corpus files, no embedding), `def load_embeddings_fixture(path: Path = EMBEDDINGS_FIXTURE) -> dict[str, list[float]]` (checks `model == settings.embedding_model` and `dim == settings.embedding_dim`), `def write_embeddings_fixture(vectors: Mapping[str, list[float]], path: Path = EMBEDDINGS_FIXTURE) -> None`.
- Fixture format: `{"model": "text-embedding-3-small", "dim": 1536, "encoding": "float32-le-base64", "embeddings": {"<chunk_key>": "<base64>"}}` (about 40 chunks, about 330 KB).

- [ ] **Step 1: Add the fixture helpers with a test** (`test_seed_embeddings_fixture.py::test_chunk_key_is_stable_and_corpus_chunks_are_deterministic`); run it; expect PASS after implementing.

- [ ] **Step 2: Export the existing embeddings for free** (the dev Chroma server still runs here)

Run `docker compose up -d`, then from `server/` a one-off script (not committed) that: builds `corpus_chunks` with placeholder asset IDs; connects with `chromadb.HttpClient(host="localhost", port=8001)`; for every collection, `get(include=["documents", "embeddings"])`; keeps each embedding whose `chunk_key(document)` matches a corpus chunk and whose length is 1536; calls `write_embeddings_fixture`; prints `found X of Y`.
Expected: `found Y of Y`. If any chunk is missing, go to Step 3; otherwise skip it.

- [ ] **Step 3 (only if Step 2 was incomplete): the paid build**

Stop: ask James for OK for one paid OpenAI call: embedding Y chunks (about 6,000 tokens) with `text-embedding-3-small` at $0.02 per million tokens, expected cost under $0.001, using his development OpenAI key (never a production key). Do not run without his explicit OK.
Run: `cd server && .venv/bin/python -m seed.build_embeddings_fixture --yes` (the script prints the token estimate and cost and refuses to call without `--yes`).

- [ ] **Step 4: Write the failing tests**

`test_seed_embeddings_fixture.py::test_every_corpus_chunk_has_a_fixture_embedding` (offline: every `chunk_key` of `corpus_chunks` is present with dim 1536; this fails if the corpus or the chunker changes without a new fixture).
`test_chroma_store.py` (real `PersistentClient` on `tmp_path`, 3-float vectors):
```python
async def test_upsert_query_count_and_delete_round_trip(tmp_path): ...  # nearest by embedding first; count 3; delete_asset leaves 1; delete_workspace leaves 0
async def test_get_by_kinds_returns_pinned_chunks(tmp_path): ...
async def test_health_is_true_for_a_local_store(tmp_path): ...
def test_telemetry_is_off(tmp_path): assert ChromaStore(path=str(tmp_path))._client.get_settings().anonymized_telemetry is False
async def test_chroma_never_loads_its_default_embedding_model(tmp_path, monkeypatch): ...  # patch DefaultEmbeddingFunction.__init__ to raise; a round trip still works
```

- [ ] **Step 5: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_chroma_store.py tests/test_seed_embeddings_fixture.py -q`
Expected: FAIL (`ChromaStore` takes no path; no `count`).

- [ ] **Step 6: Implement**

- `ChromaStore.__init__(self, path: str | None = None)`: `chromadb.PersistentClient(path=path or settings.chroma_path, settings=chromadb.config.Settings(anonymized_telemetry=False, allow_reset=False))`; collections created with `embedding_function=None`; `health()` runs `heartbeat()` in a thread; `count()` returns `collection.count()`. Docstring: one process only (two copies must never open the same directory); `PersistentClient`'s own docstring calls it a development client (chromadb/__init__.py:207-208), accepted at this scale.
- The seed's corpus step upserts with fixture vectors; a chunk missing from the fixture raises `SeedError("The embeddings fixture is out of date. Run python -m seed.build_embeddings_fixture (a paid run).")`.
- `conftest.py`, at import and before anything builds a store: point `settings.chroma_path` at `tempfile.mkdtemp(prefix="folio-test-chroma-")` and `get_vector_store.cache_clear()`, so a test run never opens the dev data directory while `npm run dev` holds it.
- CI: drop the `chroma` services, `CHROMA_HOST`/`CHROMA_PORT`, and "Wait for Chroma". Replace "Chroma client and server versions match" with a step named "No Chroma server anywhere" that fails if `grep -rn 'chromadb/chroma:' docker-compose*.yml Dockerfile .github/workflows` finds anything. Keep the four chromadb `--ignore-vuln` lines, rewording their reason: the package runs in-process only, with no server and no listener.
- `requirements.txt`: replace the RCE comment with the in-process reasoning and "watch for a patched release" (5.10 item 4).

- [ ] **Step 7: Run the tests, then the gate**

Run: Step 5 command (expected PASS); then `docker compose down --remove-orphans` (stops the old Chroma container; its volume is left alone), `docker compose up -d` (Mongo only), G-server. Then reseed dev with the dev server stopped: `npm run seed` (free: fixture vectors).

- [ ] **Step 8: Commit**

CHANGELOG: `### Security: Chroma runs in-process; the Chroma server is gone` (note: other local workspaces must reingest their assets, a paid action).
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(rag): run Chroma in-process and drop the Chroma server`

---

### Task 9: Visitor sessions: Turnstile demo start, per-IP limits, 24-hour session tokens, login closed

**Files:**
- Create: `server/app/services/turnstile.py`, `server/app/services/session_service.py`, `server/tests/test_turnstile.py`, `server/tests/test_demo_sessions.py`
- Modify: `server/app/routes/auth.py:18-56`, `server/app/utils/dependencies.py:18-38,76-84`, `server/app/utils/security.py:28-36`, `server/app/models/user.py`, `server/app/config.py`, `server/app/main.py:44-57` (CSP) and lifespan, `server/app/routes/status.py`, `server/app/database.py` (`demo_sessions` index), `server/app/utils/errors.py` (copy), `server/seed/seed_demo.py:61-80`, `server/.env.example`
- Modify tests: `test_auth.py`, `test_security_headers.py`, `test_settings_secrets.py`, `test_rate_limit.py`, `test_status.py`, `conftest.py`
- Create: `client/src/lib/turnstile.ts`, `client/src/lib/turnstile.test.ts`, `client/src/api/status.ts`
- Modify: `client/src/features/auth/useAuthActions.ts`, `client/src/features/auth/LoginPage.tsx`, `client/src/features/auth/authFlow.test.tsx`, `client/src/test/msw/handlers.ts`; `CHANGELOG.md`

**Interfaces:**
- Consumes: `ledger_visitor_id` (Task 5), `validate_serving_settings` (Task 2), `StatusResponse` (Task 4).
- Produces:
  - `turnstile.py` (a port of open-door/apps/api/app/modules/sandbox/turnstile.py, read it first): `ACTION = "demo-start"`; `class Verdict(StrEnum): PASSED, FAILED, UNAVAILABLE`; `class CloudflareVerifier(secret: str, hostname: str, client: httpx.AsyncClient | None = None)` with `async verify(token: str, remote_ip: str | None) -> Verdict` (5 s timeout; passes only on `success is True` with the expected hostname and action; `internal-error`, the misconfiguration codes, non-200, unreadable JSON, and network errors are `UNAVAILABLE`); `class TestKeyVerifier(secret: str)` (answers the test secrets locally: the pass secret with `XXXX.DUMMY.TOKEN.XXXX` passes, everything else fails; their real siteverify answers carry hostname `example.com` and no action, which the hostname and action checks would refuse); `def get_turnstile_verifier() -> TurnstileVerifier` (cached; a FastAPI dependency tests override).
  - Settings: `turnstile_site_key: str = ""`, `turnstile_secret_key: SecretStr = SecretStr("")`, `app_origin: str = "http://localhost:5173"`, `demo_starts_per_hour: int = 15`, `demo_starts_per_day: int = 50`; `def turnstile_keys(s: Settings) -> tuple[str, str]` (both blank outside production gives the always-pass test pair).
  - `validate_serving_settings` adds, in production: both Turnstile keys set; test keys only when `APP_ORIGIN` is a loopback origin (`http://localhost` or `http://127.0.0.1`, any port); `APP_ORIGIN` https unless loopback; `settings.ai_model` priced (`is_priced`).
  - `session_service.py`: `SESSION_TTL = timedelta(hours=24)`; `async def create_session(db, *, user_id: ObjectId, now: datetime | None = None) -> dict` (`_id = secrets.token_urlsafe(32)`, `user_id`, `created_at`, `expires_at`); `async def get_active_session(db, session_id: str, *, now: datetime | None = None) -> dict | None`.
  - `UserInDB.session_id: str | None = None` (never stored); `DemoStartRequest(turnstile_token: str = Field(max_length=2048))`.
  - `create_access_token` keeps its signature; the demo start passes `{"user_id", "email", "sid"}` and `expires_delta=SESSION_TTL`, and `Token.expires_in` is 86,400.
  - `get_current_user`: for `is_demo` users, a missing `sid` or no active session raises `DemoEnded` (a `UserFacingError`, 401, code `demo_ended`, `WWW-Authenticate: Bearer`); otherwise sets `user.session_id`. `ledger_visitor_id` returns `user.session_id if user.is_demo else None`.
  - `POST /api/auth/demo-login` body `DemoStartRequest`; limits `AUTH_RATE_LIMIT`, `f"{settings.demo_starts_per_hour}/hour"`, and `f"{settings.demo_starts_per_day}/day"` as slowapi callables (so tests can change them); verifies with `remote_ip=get_remote_address(request)`; `FAILED` raises 403 `BOT_CHECK_FAILED_COPY`, `UNAVAILABLE` raises 503 `BOT_CHECK_UNAVAILABLE_COPY`; no demo user raises 503 with "The demo isn't ready yet. Try again in a minute." (replacing "Run `npm run seed`", auth.py:54).
  - `POST /api/auth/login` gets a dependency that answers 404 in production (checked per request, so tests can monkeypatch `settings.environment`).
  - CSP: `script-src 'self' 'wasm-unsafe-eval' https://challenges.cloudflare.com` and a new `frame-src https://challenges.cloudflare.com`.
  - `StatusResponse` gains `turnstile_site_key: str` (the effective site key) and `password_login: bool` (`environment != "production"`).
  - Seed: in production the demo user's `hashed_password` is the bcrypt hash of a random, discarded `secrets.token_urlsafe(32)`; an existing demo user whose hash still verifies against `DEMO_PASSWORD` is re-hashed.
  - Client: `getTurnstileToken(slot: HTMLElement, siteKey: string, action?: string): Promise<string>` in `client/src/lib/turnstile.ts` (a port of open-door/apps/web/src/lib/turnstile.ts: script loaded on press with `render=explicit`, 10 s script timeout, one single-use widget per start, `interaction-only` appearance, site key passed in rather than read from a meta tag); `useAppStatus()` in `client/src/api/status.ts` (react-query, `staleTime: 30_000`) returning `AppStatus { live_ai_available: boolean; live_ai_reason: "available" | "off" | "paused"; turnstile_site_key: string; password_login: boolean }`; `loginDemo(slot: HTMLElement | null)` sends `{ turnstile_token }` (empty when no token could be had, so the server's own refusal text shows).

- [ ] **Step 1: Write the failing tests**

`test_turnstile.py` (`httpx.MockTransport`): `test_a_token_passes_only_with_the_right_hostname_and_action`; `test_a_wrong_hostname_or_action_fails`; `test_cloudflare_trouble_is_unavailable` (parametrized: `internal-error`, HTTP 500, unreadable JSON, a network error, `invalid-input-secret`); `test_an_empty_token_fails_without_a_request`; `test_the_test_secrets_are_answered_locally` (pass secret with the dummy token passes; always-fail secret fails; pass secret with another token fails); `test_build_picks_the_local_verifier_only_for_test_secrets`.
`test_demo_sessions.py`:
```python
async def test_a_demo_start_without_a_valid_token_is_refused(client): ...  # 403, BOT_CHECK_FAILED_COPY, no session doc
async def test_a_demo_start_creates_a_24_hour_session(client, test_db): ...  # 200; JWT has sid; exp - iat == 86_400; session expires_at == created_at + 24h
async def test_an_unreachable_bot_check_is_a_503(client): ...
async def test_demo_starts_are_limited_per_ip_per_hour_and_per_day(client, monkeypatch, enabled_limiter): ...  # per hour 2: third is 429 RATE_LIMITED_COPY; then per day the same
async def test_a_demo_token_without_a_session_claim_is_demo_ended(client, test_db): ...  # 401 {"detail": DEMO_ENDED_COPY, "code": "demo_ended"}
async def test_an_expired_or_deleted_session_is_demo_ended(client, test_db): ...
async def test_owner_tokens_need_no_session(client, test_db): ...
async def test_login_is_404_in_production_and_works_in_development(client, test_db, monkeypatch): ...
async def test_the_seed_gives_the_demo_user_an_unusable_password_in_production(test_db, monkeypatch): ...  # DEMO_PASSWORD no longer verifies
async def test_the_ledger_counts_spend_per_session(client, test_db): ...  # a text generation by a demo session writes ai_spend_visitors[sid]
```
`test_settings_secrets.py`: production without Turnstile keys fails; test keys with `https://folio.example.com` fail; test keys with `http://localhost:8000` pass; `http://` non-loopback origin fails.
`test_security_headers.py`: the CSP contains `script-src 'self' 'wasm-unsafe-eval' https://challenges.cloudflare.com` and `frame-src https://challenges.cloudflare.com`.
`test_status.py`: `turnstile_site_key == "1x00000000000000000000AA"` in development with blank keys; `password_login` false in production.
Client `authFlow.test.tsx`: `sends the Turnstile token with the demo start` (mock `@/lib/turnstile` to resolve `"tok"`; MSW asserts the body); `hides the password sign-in when the server says so` (`password_login: false`). `turnstile.test.ts`: port the script-timeout and widget-callback tests from Open Door's suite if it has them; at minimum `rejects when the script never loads`.

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_turnstile.py tests/test_demo_sessions.py tests/test_settings_secrets.py tests/test_security_headers.py tests/test_status.py -q` and `cd client && npx vitest run src/features/auth src/lib/turnstile.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says. Add `demo_sessions` to `TEST_COLLECTIONS`; index `demo_sessions.expires_at`. Move the `enabled_limiter` fixture from `test_rate_limit.py` into `conftest.py` (Tasks 9 and 14 share it); `test_rate_limit.py` now sends a token body and overrides the verifier, so its unseeded starts answer 503 until the limit's 429. `.env.example`: the Turnstile pair (blank means test keys in development), `APP_ORIGIN`, the two start limits. In `LoginPage.tsx`, the "Explore as demo" button passes a slot element rendered under it.

- [ ] **Step 4: Run the tests, then the gates**

Run: Step 2 commands (expected PASS), then G-server and G-client. Smoke: `npm run dev`, press "Explore as demo": the test widget passes and the dashboard opens.

- [ ] **Step 5: Commit**

CHANGELOG: `### Security: visitor sessions behind a bot check; password sign-in closed in production`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat: visitor sessions behind Turnstile, 24-hour tokens, login closed in production`

---

### Task 10: Session-scoped History and downloads, a read-only examples rule, hourly cleanup of expired sessions

**Files:**
- Modify: `server/app/services/generations_service.py:19-155`, `server/app/routes/generations.py:28-140`, `server/app/routes/documents.py:121-183`, `server/app/routes/generate.py` (the three `create_generation` calls), `server/app/models/generation.py:218-231` (`is_example`), `server/app/database.py` (indexes), `server/app/jobs/cleanup.py`, `server/app/utils/errors.py` (`ExampleReadOnly`)
- Create: `server/tests/test_session_isolation.py`; modify `server/tests/test_cleanup_job.py`, `test_generations_patch.py`, `test_pagination.py`, `test_isolation.py`
- Modify: `client/src/types/index.ts:280-294` (`is_example: boolean`); `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `def scope_filter(workspace_oid: ObjectId, session_id: str | None) -> dict`: `{"workspace_id": ws}` for owners; `{"workspace_id": ws, "$or": [{"session_id": session_id}, {"is_example": True}]}` for a visitor.
  - `list_generations`, `count_generations`, `get_generation` take `session_id: str | None` (keyword-only) and use `scope_filter`. `update_generation_output` and `delete_generation` take `session_id` and add `"is_example": {"$ne": True}` plus `"session_id": session_id` for a visitor.
  - `create_generation(..., session_id: str | None = None, expires_at: datetime | None = None)`; the routes pass `current_user.session_id` and, for a visitor, the session's `expires_at` (read once in `get_current_user` and kept as `UserInDB.session_expires_at: datetime | None = None`).
  - `GenerationResponse.is_example: bool = False` (the session ID is never returned).
  - `class ExampleReadOnly(UserFacingError)`: 403, code `example_read_only`, `EXAMPLE_READ_ONLY_COPY`.
  - `DELETE /generations/{id}` drops `require_not_demo`: a visitor may delete its own work; examples are 403 for everyone.
  - `run_cleanup` also returns `expired_generations` and `expired_sessions`: for each visitor generation with `expires_at <= now`, delete its document files (`build_document_prefix`) first, then the records; then delete sessions with `expires_at <= now` and their `ai_spend_visitors` docs (`ai_ledger.delete_visitor`). Ledger day docs are never touched.
  - Indexes: `generations (workspace_id, session_id, created_at -1)`, `generations expires_at`, and (Task 11) the example key.

- [ ] **Step 1: Write the failing tests** (`test_session_isolation.py`: two real sessions A and B on the demo workspace, with one example, one A text, one A card, one A document with files)

```python
async def test_visitors_see_only_their_own_work_and_the_examples(two_visitors): ...  # list and count for A: A's three + example; for B: the example only
@pytest.mark.parametrize("verb", ["get", "patch", "delete", "download"])
async def test_a_visitor_cannot_reach_another_visitors_generation(two_visitors, verb): ...  # B on A's ids: 404, A's docs unchanged, files still there
async def test_examples_are_readable_by_everyone_and_editable_by_no_one(two_visitors, owner): ...  # GET 200; PATCH and DELETE 403 EXAMPLE_READ_ONLY_COPY (A, B, owner)
async def test_a_visitor_can_delete_their_own_generation_and_its_files(two_visitors): ...
async def test_new_generations_carry_the_session_and_its_expiry(client, test_db): ...
```
`test_cleanup_job.py`:
```python
async def test_cleanup_removes_expired_visitor_work_files_first(test_db, tmp_storage): ...  # files then records; live session untouched; examples untouched
async def test_a_failed_file_delete_keeps_the_records_for_the_next_run(test_db, failing_storage): ...  # records remain, job exits non-zero
async def test_cleanup_removes_expired_sessions_and_their_visitor_spend_but_not_day_totals(test_db): ...
def test_the_cleanup_job_never_imports_chroma(): ...  # subprocess: import app.jobs.cleanup; assert "chromadb" not in sys.modules
```

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_session_isolation.py tests/test_cleanup_job.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says. The PATCH route reads with `scope_filter` first: an example is 403, another visitor's is 404.

- [ ] **Step 4: Run the tests, then the gates**

Run: Step 2 command plus `tests/test_generations_patch.py tests/test_pagination.py tests/test_isolation.py tests/test_documents.py` (expected PASS), then G-server and G-client.

- [ ] **Step 5: Commit**

CHANGELOG: `### Security: each visitor's History is private; work is removed after 24 hours`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(server): scope History and downloads to the visitor session and clean up hourly`

---

### Task 11: Self-healing seed at startup, read-only example generations, public examples API

D1 is decided (James accepted startup seeding inside the app process on 2026-11-19), so no stop is needed here.

**Files:**
- Modify: `server/seed/seed_demo.py` (whole file), `server/app/main.py` (lifespan; examples router), `server/app/config.py` (`seed_on_startup: bool = False`), `server/app/database.py` (partial unique index on `example_key`), `server/app/models/generation.py` (`ExamplesResponse`)
- Create: `server/seed/fixtures/examples.json`, `server/app/routes/examples.py`, `server/tests/test_seed_self_healing.py`, `server/tests/test_examples_api.py`, `server/tests/test_visitor_copy.py`
- Modify: `server/tests/test_seed_demo.py`, `server/.env.example` (`SEED_ON_STARTUP=true` for local dev, with a comment), `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `@dataclass class SeedReport: created: list[str]; repaired: list[str]; error: str | None` with `ok` property.
  - `async def ensure_demo_seed(db, *, store: VectorStore, storage: StorageBackend, embed_missing: bool = False) -> SeedReport`, checking and repairing in this order: demo user (unusable password in production, Task 9); workspace; each corpus asset record and its stored file (re-saved from `seed/verdure_corpus/`); the Chroma collection (`store.count(namespace)` equal to the sum of the assets' `chunk_count`, else drop and re-upsert from the fixture; `embed_missing=True` is the only path that calls OpenAI, through the ledger); `ready_chunk_count`; logo, exemplars, brand images, and templates (record and file; a missing file is regenerated at the same key); the four examples (by `example_key`; a document example also needs every rendered file).
  - Startup: when `settings.seed_on_startup`, the lifespan runs `ensure_demo_seed` after the indexes and stores the report on `app.state.seed_report`. An exception is logged and recorded as `SeedReport(error=...)`; the app still starts, and readiness reports it (Task 14).
  - CLI: `python -m seed.seed_demo [--embed-missing]` prints the report; its docstring says to stop the API first (one process per Chroma directory).
  - Examples: generation docs with `is_example: True`, `example_key`, `session_id: None`, no `expires_at`, `owner_id` the demo user, `model` = `settings.ai_model`; text and post captions go through `parse_post`; document formats are rendered with `document_service.build_document_files(document, brand_profile, {})` in a thread and saved at `build_document_key`; `retrieval_meta` comes from the fixture's `retrieval` entries (`filename`, `chunk_index`, `score`, `pinned`), resolved to the seeded asset IDs, chunk IDs (`f"{asset_id}:{chunk_index}"`), and the first 240 characters of the chunk text.
  - `GET /api/examples` (no auth, slowapi `60/minute`, cached in process for 60 s, `Cache-Control: public, max-age=60`): `ExamplesResponse(workspace_name: str, brand: BrandProfile subset {colors, fonts, accent_hex, voice_summary}, items: list[GenerationResponse])`, empty `items` when nothing is seeded (never a 500). `GET /api/examples/{generation_id}/download/{fmt}`: example document generations only, storage key rebuilt server-side, else 404.
- `examples.json` (written by hand in this task, American English, no em dashes, facts only from `server/seed/verdure_corpus/`): `text-post` (type `text`, tone default, a LinkedIn post with hashtags); `card` (type `card`, template `statement`, accent `#C98A3D`, no image); `post-pack` (type `post_pack`, caption plus a `quote` card, no image); `document` (type `document`, archetype `one-pager`, three sections with bullets). Cards carry no image because History and the examples page render uploaded images only inside Generate (CardThumb.tsx:5-11).

- [ ] **Step 1: Write the failing tests**

`test_seed_self_healing.py` (real `test_db`, `FakeVectorStore` with `count`, a `tmp_path` `LocalStorage`, and a fixture loader patched to deterministic vectors for every corpus chunk):
```python
async def test_a_fresh_database_is_seeded_completely(seed_env): ...  # user, workspace, 5 assets, count == chunks, files exist, 4 examples, document pdf and docx exist
async def test_a_second_run_repairs_nothing(seed_env): ...  # report.created == report.repaired == []
async def test_seed_repairs_missing_files_collection_and_examples_without_paid_calls(seed_env): ...
    # delete a corpus file, the logo file, the example pdf, the collection, and the card example;
    # embedder that raises if called; run again: all present; report.repaired names each one
async def test_an_out_of_date_fixture_is_an_error_without_embed_missing(seed_env): ...
async def test_examples_are_marked_read_only_and_resolve_their_retrieval(seed_env): ...
```
`test_examples_api.py`: `test_examples_are_public_and_cached` (no Authorization header; 200; four items all `is_example`; `Cache-Control: public, max-age=60`); `test_an_example_document_downloads_without_signing_in` (pdf 200 `application/pdf`); `test_a_non_example_id_is_404`; `test_no_seed_means_an_empty_list`.
`test_visitor_copy.py`: `test_no_em_dashes_in_visitor_copy_or_fixtures` scans `seed/fixtures/examples.json`, every `*_COPY` constant in `app/utils/errors.py` and `app/routes/*.py`, and `client/src/**/*.tsx` string literals added by this plan (`StartPage`, `ExamplesPage`, `PrivacyPage`, `GenerationError`), asserting `"\u2014" not in text` (the em dash code point, written as an escape). (Existing older copy is out of scope.)

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_seed_self_healing.py tests/test_examples_api.py tests/test_visitor_copy.py tests/test_seed_demo.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says.

- [ ] **Step 4: Run the tests, then the gate**

Run: Step 2 command (expected PASS), then G-server. Stop the dev API, run `npm run seed` twice (second run: nothing repaired), then `npm run dev` and open `http://localhost:8000/api/examples`.

- [ ] **Step 5: Commit**

CHANGELOG: `### Added: ready-made examples and a seed that repairs itself`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(server): self-healing seed with read-only example generations`

---

### Task 12: Client free path: start page and public examples page

**Files:**
- Create: `client/src/features/start/StartPage.tsx`, `client/src/features/start/StartPage.test.tsx`, `client/src/features/examples/ExamplesPage.tsx`, `client/src/features/examples/ExamplesPage.test.tsx`, `client/src/api/examples.ts`
- Create (copies of `docs/screenshots/`): `client/public/screenshots/linkedin-post.jpg`, `image-card.jpg`, `document.jpg`, `retrieved-context.jpg`
- Modify: `client/src/App.tsx`, `client/src/features/history/HistoryCard.tsx`, `client/src/features/generate/DocumentDownloadRow.tsx`, `client/src/features/generate/documentDownload.ts`, `client/src/types/index.ts`, `client/src/test/msw/handlers.ts`, `client/src/features/auth/LoginPage.tsx` (dev-only sign-in page); `CHANGELOG.md`

**Interfaces:**
- Consumes: `useAppStatus` and `getTurnstileToken` (Task 9); `GET /api/examples` (Task 11).
- Produces:
  - Routes: signed out, `/` is `StartPage`; signed in, `/` is the dashboard. `/examples` is public. `/login` is the dev sign-in page and redirects to `/` when `password_login` is false. `RequireAuth` redirects to `/` (not `/login`).
  - `useExamples()` in `client/src/api/examples.ts` (react-query, `staleTime: 60_000`); `ExamplesResponse` type.
  - `HistoryCard` gains `readOnly?: boolean` (no delete or edit actions) and `downloadUrl?: (fmt: DocumentFormat) => string`; `DocumentDownloadRow` and `documentDownload.ts` accept the same `downloadUrl` builder (default: the authed workspace URL). The examples page passes `` (fmt) => `/examples/${id}/download/${fmt}` ``.
  - Start page content: Folio's one-line pitch; a primary "Try it live" button (Turnstile slot beneath it; on success, the dashboard); right beside it, "See ready-made examples" (a link to `/examples` that needs no demo start and no bot check); when `live_ai_available` is false, a notice with `LIVE_AI_PAUSED_COPY` shown before the button, and the button reads "Explore the studio" instead; a strip of the four screenshots with alt text; the dev password form only when `password_login` is true.

- [ ] **Step 1: Write the failing tests**

`StartPage.test.tsx`:
```tsx
it("offers the live demo and the examples side by side", ...)  // both controls visible, no token requested yet
it("says live generation is paused before the bot check when the status says so", ...)
it("starts a demo with a Turnstile token and lands on the dashboard", ...)  // mock getTurnstileToken -> "tok"
it("shows the server's refusal text when the bot check fails", ...)  // 403 BOT_CHECK_FAILED_COPY
it("never shows the password form in production", ...)  // password_login false
it("sends a signed-out deep link back to the start page", ...)  // /history -> start page
```
`ExamplesPage.test.tsx`:
```tsx
it("lists the four examples without signing in", ...)  // MSW handler asserts no Authorization header
it("marks every item as an example and offers no edit or delete", ...)
it("downloads a document example from the public URL", ...)
```

- [ ] **Step 2: Run to see them fail**

Run: `cd client && npx vitest run src/features/start src/features/examples`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says, following DESIGN.md tokens (no hardcoded hex) and the design skills named in docs/WORKFLOW.md section 2. Inject brand fonts from the examples response's `brand` with `injectBrandFontFaces`, as `HistoryPage` does.

- [ ] **Step 4: Run the tests, then the gate**

Run: Step 2 command (expected PASS), then G-client. Manual: `npm run dev`, signed out: `/` shows both paths; `/examples` renders the four examples and downloads the PDF.

- [ ] **Step 5: Commit**

CHANGELOG: `### Added: a start page with a free path to ready-made examples`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(client): start page and public examples as the free path`

---

### Task 13: Client session experience: demo ended, read-only examples, visitor delete, refusals that point at the examples

**Files:**
- Create: `client/src/features/generate/GenerationError.tsx`, `client/src/features/generate/GenerationError.test.tsx`
- Modify: `client/src/stores/auth.ts`, `client/src/lib/api.ts:14-22`, `client/src/lib/sse.ts:13-17,45-87,133-136`, `client/src/lib/apiError.ts`, `client/src/features/generate/useStreamedGeneration.ts`, `client/src/features/generate/modes/TextMode.tsx`, `CardPreview.tsx`, `DocumentPreview.tsx`, `PostCaptionPanel.tsx`, `client/src/features/generate/GeneratePage.tsx`, `client/src/features/history/HistoryCard.tsx`, `DetailDialog.tsx:35,172`, `client/src/components/layout/SideNav.tsx`, `client/src/components/DemoNotice.tsx`, `client/src/features/start/StartPage.tsx`
- Modify tests: `client/src/stores/auth.test.ts`, `client/src/lib/sse.test.ts`, `client/src/features/history/HistoryPage.test.tsx`, `client/src/components/layout/SideNav.test.tsx`; `CHANGELOG.md`

**Interfaces:**
- Produces:
  - Auth store: `endedReason: "ended" | null`; `logout(reason?: "ended")`; `endedReason` is not persisted.
  - A 401 from axios or from `openStream` for a demo user calls `logout("ended")`; the start page shows `DEMO_ENDED_COPY` in a banner.
  - `StreamHandlers.onError(message: string, code?: string)`; `StreamBaseState.errorCode: string | null`; `apiErrorCode(err: unknown): string | null`.
  - `GenerationError({ message, code })`: the message, plus a "Browse the ready-made examples" link to `/examples` when `code` is `live_ai_paused`, `visitor_allowance`, `live_ai_unavailable`, or `rate_limited`. Used everywhere a generation error renders today (TextMode, CardPreview, DocumentPreview, PostCaptionPanel) and for the template AI fill errors.
  - History: an "Example" badge on examples; examples never show Delete or "Edit in Generate"; a visitor's own items show Delete (DetailDialog.tsx:172 changes from `!isDemo` to `!gen.is_example`).
  - Sign-out for a demo user confirms first: title "End your demo?", body "Signing out ends this demo. Your work stays private and is removed after 24 hours.", confirm "End demo" (reuse `ConfirmDialog`).
  - `DemoNotice` default copy: "You're exploring a private demo. Brand settings and assets are read-only so every visitor sees the same sample brand. Generating posts, cards, and documents still works, and your work is removed after 24 hours."
  - The Generate page shows `LIVE_AI_PAUSED_COPY` and the examples link above the brief when `useAppStatus` says live AI is unavailable.

- [ ] **Step 1: Write the failing tests**

```tsx
// auth.test.ts / StartPage.test.tsx
it("a 401 logs out and shows the demo ended banner", ...)  // test_a_401_logs_out_and_shows_the_demo_ended_banner
// sse.test.ts
it("a 401 on a stream ends the demo session", ...)
it("passes the error code from an error frame", ...)
// GenerationError.test.tsx
it.each(["live_ai_paused", "visitor_allowance", "live_ai_unavailable", "rate_limited"])("links to the examples for %s", ...)
it("shows no examples link for other errors", ...)
// HistoryPage.test.tsx
it("badges examples and offers no delete or edit on them", ...)
it("lets a visitor delete their own generation", ...)
// SideNav.test.tsx
it("asks before a demo visitor signs out", ...)
```

- [ ] **Step 2: Run to see them fail**

Run: `cd client && npx vitest run src/stores src/lib src/features/generate/GenerationError.test.tsx src/features/history src/components/layout`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says.

- [ ] **Step 4: Run the tests, then the gates**

Run: Step 2 command (expected PASS), then G-client and G-server.

- [ ] **Step 5: Commit**

CHANGELOG: `### Added: a clear end to a demo, and refusals that point at the examples`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(client): demo-ended path, read-only examples, and refusals that point at examples`

---

### Task 14: Container and operations: health checks, Mongo pool, write check, threads, Unsplash limit and cache, local production compose

**Files:**
- Modify: `server/app/routes/health.py`, `server/app/database.py:24-27`, `server/app/config.py:28` (`database_name` default `folio`; `mongo_max_pool_size: int = 10`), `server/app/main.py` (lifespan write check), `server/app/services/storage_service.py`, `server/app/routes/documents.py:110-112`, `server/app/services/brand_extract_service.py:101`, `server/app/services/unsplash_service.py`, `server/app/routes/images.py:35-60`, `server/app/utils/ratelimit.py`, `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml` (docker job), `server/.env.example:12-14`
- Create: `docker-compose.prod.yml`, `server/tests/test_health.py`, `server/tests/test_storage_writable.py`
- Modify tests: `test_unsplash.py`, `test_dockerfile.py`; `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `GET /api/health/live` returns `{"status": "ok"}` and never touches a database. `GET /api/health` checks Mongo (`ping`), the vector store, and (when `seed_on_startup`) `app.state.seed_report.ok`, each under `asyncio.wait_for(..., 2.0)`, returning 200 `{"status": "ok", "mongo": true, "vector_store": true, "seed": true}` or 503 with the same keys.
  - `connect_to_mongo` uses `maxPoolSize=settings.mongo_max_pool_size`, `serverSelectionTimeoutMS=5000`.
  - `def assert_writable(path: Path) -> None` in `storage_service.py` raises `StorageNotWritable(f"{path} is not writable by uid {os.getuid()}")` after a create-and-delete probe; the lifespan calls it for `settings.storage_local_dir` and `settings.chroma_path` before the vector store and the seed.
  - Document rendering (`build_document_files`) and palette extraction (`extract_palette`) run in `asyncio.to_thread`.
  - Unsplash: `RATE_LIMIT_UNSPLASH = settings.rate_limit_unsplash` (`"20/minute"`) on search and track; search results cached in process for 1 hour, at most 256 entries, keyed by `(query.casefold().strip(), page)`. `UnsplashError` text and the route's 502 detail become "Image search isn't available right now. You can still use the brand images." (replacing unsplash_service.py:39 "Set UNSPLASH_ACCESS_KEY in server/.env" and images.py:47's status text).
  - Dockerfile: `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STORAGE_LOCAL_DIR=/app/storage CHROMA_PATH=/app/chroma SEED_ON_STARTUP=true DATABASE_NAME=folio`; `mkdir -p /app/storage /app/chroma` owned by 10001; `HEALTHCHECK` probes `/api/health/live`; a comment that the server must run one worker (Chroma in-process).
  - `.dockerignore` gains `server/chroma/`.
  - `docker-compose.prod.yml`: a user-defined network `folio_local` with subnet `172.30.0.0/24`; `mongo` (mongo:7, no published port, volume `folio_mongo`); `app` (`build: .`, image `folio:local`, `ports: ["127.0.0.1:8000:8000"]`, volumes `folio_storage:/app/storage` and `folio_chroma:/app/chroma`, `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`, `mem_limit: 1024m`, `stop_grace_period: 30s`). Environment set inline: `ENVIRONMENT=production`, `APP_ORIGIN=http://localhost:8000`, `CORS_ORIGINS=["http://localhost:8000"]`, `FORWARDED_ALLOW_IPS=127.0.0.1,172.30.0.0/24`, `MONGODB_URL=mongodb://mongo:27017`, `TURNSTILE_SITE_KEY=1x00000000000000000000AA`, `TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA`, `AI_MONTHLY_BUDGET_USD=${AI_MONTHLY_BUDGET_USD:-0}`, `DEMO_STARTS_PER_HOUR=${DEMO_STARTS_PER_HOUR:-15}`, `ANTHROPIC_API_KEY=placeholder-never-called`, `OPENAI_API_KEY=` (empty), `JWT_SECRET_KEY=${JWT_SECRET_KEY:?Set JWT_SECRET_KEY, for example with openssl rand -hex 32}`. Named volumes start owned by uid 10001 (copied from the image).
  - CI docker job: run the image with `--network host` and `-e MONGODB_URL=... -e JWT_SECRET_KEY=... -e APP_ORIGIN=http://localhost:8000 -e FORWARDED_ALLOW_IPS=127.0.0.1 -e TURNSTILE_SITE_KEY=<test> -e TURNSTILE_SECRET_KEY=<test> -e AI_MONTHLY_BUDGET_USD=0`; wait for `healthy`; assert `/api/health` is `ok` with `seed: true` (the seed ran from fixtures with no OpenAI key); `/api/examples` has 4 items; `POST /api/auth/login` is 404; the CSP header contains `https://challenges.cloudflare.com`; keep the bundle and 404 checks.

- [ ] **Step 1: Write the failing tests**

```python
# test_health.py
async def test_liveness_never_touches_the_database(): ...  # get_database overridden to raise: still 200
async def test_readiness_is_503_within_about_two_seconds_when_mongo_hangs(): ...  # a fake db whose command sleeps 10 s: 503 in < 3 s
async def test_readiness_is_200_when_everything_answers(): ...
async def test_readiness_is_503_when_the_seed_failed(): ...  # app.state.seed_report = SeedReport(error="x")
# test_storage_writable.py
def test_startup_refuses_an_unwritable_storage_dir(tmp_path): ...  # chmod 0o500 dir: StorageNotWritable naming the path (skip when running as root)
# test_unsplash.py
async def test_search_results_are_cached(monkeypatch): ...  # two identical searches, one upstream call
async def test_search_is_limited_per_ip(enabled_limiter): ...  # 21st in a minute: 429 RATE_LIMITED_COPY
async def test_an_unconfigured_key_reads_plainly(): ...
# test_dockerfile.py
def test_the_image_checks_liveness_and_sets_the_data_paths(): ...
```

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_health.py tests/test_storage_writable.py tests/test_unsplash.py tests/test_dockerfile.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says. `.env.example`: `DATABASE_NAME=folio` with a note that an existing local `.env` keeps its own value.

- [ ] **Step 4: Run the tests, then the gates; build the image**

Run: Step 2 command (expected PASS), G-server, G-client, then `docker build -t folio:local .` (expected: success).

- [ ] **Step 5: Commit**

CHANGELOG: `### Changed: liveness and readiness checks, a smaller Mongo pool, and a local production run`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `build: health checks, Mongo pool, write check, and a local production compose`

---

### Task 15: Visitor-facing copy: developer text, a privacy and terms page, link previews

**Files:**
- Create: `client/src/features/privacy/PrivacyPage.tsx`, `client/src/features/privacy/PrivacyPage.test.tsx`, `client/public/og-image.jpg` (a copy of `docs/screenshots/linkedin-post.jpg`)
- Modify: `client/src/App.tsx` (public `/privacy`), `client/src/features/start/StartPage.tsx` and `client/src/components/layout/SideNav.tsx` (a "Privacy and terms" link), `client/index.html`, `server/app/spa.py`, `server/app/main.py:205-206`, `server/app/utils/dependencies.py:82`, `client/src/lib/sse.ts:65`, `client/src/features/auth/useAuthActions.ts:31`
- Modify tests: `server/tests/test_spa.py`, `client/src/lib/sse.test.ts`, `client/src/features/auth/authFlow.test.tsx`; `CHANGELOG.md`

**Interfaces:**
- Produces:
  - Copy replacements (exact): dependencies.py:82 becomes "This part of the demo is read-only, so the sample brand stays the same for every visitor."; sse.ts:65 becomes "Network error. Check your connection and try again."; useAuthActions.ts:31 becomes "The demo couldn't start. Try again in a moment."
  - `PrivacyPage` (public, title "Privacy and terms") with this copy:
    - "Folio is a portfolio project by James Littlefield. The public demo has no accounts: each visit starts a private demo session that only you can see."
    - "Retention: removed from the app after 24 hours; backups up to 7 days; server logs (including IP addresses) 14 days."
    - "Services that process demo data: Anthropic (writes the content), OpenAI (embeds briefs to find matching brand material), Cloudflare (the bot check), Unsplash (image search), AWS (hosting), and MongoDB Atlas (the database)."
    - "Please don't enter personal or confidential information."
    - "Terms: the demo is provided as is, for evaluation only. Content is written by AI and may be inaccurate. Live generation has a budget and may pause; the ready-made examples are always available."
    - A link to `https://jameslittlefield.net`.
  - `client/index.html` gains `<meta name="description">`, `og:title` ("Folio, an on-brand content studio"), `og:description` ("A retrieval-augmented studio that writes on-brand LinkedIn posts, cards, and documents. Try it live, no sign-up."), `og:type` `website`, `og:url` `__APP_ORIGIN__/`, `og:image` `__APP_ORIGIN__/og-image.jpg`, `twitter:card` `summary_large_image`.
  - `mount_spa(app: FastAPI, dist_dir: Path, *, app_origin: str) -> None`: `index.html` is read once, `__APP_ORIGIN__` is replaced with `app_origin` (no trailing slash), and served from memory with `Cache-Control: no-cache` on both index paths.

- [ ] **Step 1: Write the failing tests**

`test_spa.py`: `test_index_html_carries_the_app_origin_in_link_previews` (the fixture index has `__APP_ORIGIN__`; the served HTML has `https://folio.example.com/og-image.jpg` and no placeholder, for `/`, `/index.html`, and a client route).
`PrivacyPage.test.tsx`: `states the retention and names every processor` (the exact retention sentence; each of the six processor names); `is reachable signed out`.
`sse.test.ts` and `authFlow.test.tsx`: the new network and demo-start texts; neither contains "server running".

- [ ] **Step 2: Run to see them fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_spa.py -q` and `cd client && npx vitest run src/features/privacy src/lib/sse.test.ts src/features/auth`
Expected: FAIL.

- [ ] **Step 3: Implement** as the Interfaces block says.

- [ ] **Step 4: Run the tests, then the gates**

Run: Step 2 commands (expected PASS), then G-server and G-client.

- [ ] **Step 5: Commit**

CHANGELOG: `### Added: a privacy and terms page, link previews, and plain error text`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `feat(client): privacy and terms page, link previews, and visitor-facing error text`

---

### Task 16: CI security hardening: gitleaks, read-only permissions, SHA-pinned actions

Stop first for Step 4: confirm D6 with James.

**Files:**
- Create: `.github/workflows/security.yml`
- Modify: `.github/workflows/ci.yml` (pins, `persist-credentials: false`, `timeout-minutes`), `docs/WORKFLOW.md:114,129` (the new workflow and its job name); `CHANGELOG.md`

**Interfaces:**
- Produces: a workflow `Security` with one job, name `Leaked secrets (gitleaks)`, ported from open-door/.github/workflows/security.yml:1-41 (same triggers: push to `main` and `dev`, every pull request, weekly `0 13 * * 1`, `workflow_dispatch`; the same concurrency rule; `permissions: contents: read`; checkout `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` with `persist-credentials: false` and `fetch-depth: 0`; gitleaks 8.30.1 downloaded and checksum-verified; `./gitleaks git --redact --verbose --exit-code 1`). Folio's own dependency audit stays in ci.yml's `audit` job, which already runs weekly (ci.yml:10-11) with read-only permissions (ci.yml:19-20).

- [ ] **Step 1: Pin every action in ci.yml**

`actions/checkout@v7` becomes `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`; `actions/setup-node@v7` becomes `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0` (both from Open Door). For `actions/setup-python`, resolve the newest v7 tag: `gh api repos/actions/setup-python/releases/latest --jq .tag_name`, then `gh api repos/actions/setup-python/git/ref/tags/<tag> --jq .object.sha` (dereference an annotated tag with `gh api repos/actions/setup-python/git/tags/<sha> --jq .object.sha`), and pin `@<sha> # <tag>`. The docker actions are already pinned (ci.yml:146-147). Add `persist-credentials: false` to every checkout and `timeout-minutes` (15 for server and docker, 10 otherwise).

- [ ] **Step 2: Add `security.yml`** as the Interfaces block says.

- [ ] **Step 3: Check the workflows**

Run: `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color` (pulls a free image)
Expected: no findings. Then `grep -rnE 'uses: [^@]+@v[0-9]' .github/workflows` finds nothing.

- [ ] **Step 4: No `dependabot.yml`** (D6 decided by James on 2026-11-19: security fixes only, through the GitHub setting in master plan Phase 0, plus the weekly audits). Nothing to add; the step stays so numbering doesn't shift.

- [ ] **Step 5: Gitleaks over the full history after the first push**

The first CI run on the pushed branch (Task 18) scans all history. If it flags a known placeholder (for example a test value in `ci.yml` or `tests/`), stop, show James each finding, and with his OK add a `.gitleaksignore` with those fingerprints only.

- [ ] **Step 6: Commit**

CHANGELOG: `### Security: gitleaks in CI and every action pinned to a SHA`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `ci: add gitleaks and pin every action to a SHA`

---

### Task 17: Docs: decisions, README, architecture, data model, deploy reference, superseded plans, CLAUDE.md

**Files:**
- Create: `docs/DEPLOY.md`
- Modify: `docs/DECISIONS.md` (header line 7; rows #1, #2, #7, #17, #35, #40 notes; new rows #41 to #46), `docs/PLAN.md` (banner), `docs/aws_infrastructure_plan.md` (banner), `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/WORKFLOW.md` (section 5 CI paragraph), `README.md` (Local development, Settings, Production image, demo description), `CLAUDE.md` (commands), `server/.env.example` (final pass), `CHANGELOG.md`

**Interfaces:** none (documentation only). Every sentence follows the writing rules; new DECISIONS rows use no em dashes even though older rows do.

- [ ] **Step 1: DECISIONS.md**

New rows, each with Area, Decision, Supersedes, Rationale, and file pointers:
- #41 Public demo without accounts: Turnstile-checked demo start, per-IP limits, 24-hour sessions carried in the JWT, History scoped per session, examples read-only, login 404 in production, unusable demo password (supersedes the "Explore as demo" shared login of #9 and #15).
- #42 AI dollar ledger with daily pacing and per-visitor allowance (supersedes #35's daily count and #17's deferred in-app caps).
- #43 Server-side fallbacks off; one shared client; timeouts; no SDK retries (amends #40).
- #44 Chroma in-process via PersistentClient, no Chroma server, single process, stop-then-start deploys (supersedes #1's Qdrant for production; the Qdrant stub is removed).
- #45 Self-healing seed from checked-in fixtures (embeddings and examples), run at startup (D1, D2 as James decided).
- #46 Deployment: one EC2 server managed by ECS behind an ALB, MongoDB Atlas M0, storage and Chroma on the retained data volume; health live and ready; uvicorn trust and keep-alive (supersedes #2's Fargate and #7's self-hosted Mongo), pointing at the portfolio-infra design.
Update line 7 to "Rows run through #46 (2026-11-19)".

- [ ] **Step 2: Superseded banners**

At the top of `docs/PLAN.md` and `docs/aws_infrastructure_plan.md`: "> **Superseded for deployment (2026-11-19).** The deployment now follows the portfolio-infra design (`../portfolio-infra/docs/design/2026-11-18-portfolio-apps-aws-deployment-design.md`) and this repo's `docs/superpowers/plans/2026-11-19-demo-sessions-and-deploy-readiness.md`. Kept for history."

- [ ] **Step 3: `docs/DEPLOY.md`**

Copy the "ECS reference for Phase 2" tables from the end of this plan, plus: the local production run (`export JWT_SECRET_KEY=$(openssl rand -hex 32)`, then `docker compose -f docker-compose.prod.yml up -d --build`), how to read the seed report in the logs, the restore note (attach the retained volume or a snapshot; startup reseeds what is missing at no cost), and "start the production database empty".

- [ ] **Step 4: README, ARCHITECTURE, DATA_MODEL, WORKFLOW, CLAUDE.md**

README: Mongo only in `docker compose`; the API seeds itself at startup (`SEED_ON_STARTUP=true` in `.env.example`) and `npm run seed` runs with the API stopped; Turnstile test keys are the default in development; the new settings table rows (every env name in Global Constraints, with defaults); the production image section points at `docs/DEPLOY.md`; the demo description (one click, private, 24 hours, examples). ARCHITECTURE: the ledger flow (reserve before the response, settle shielded), sessions, Chroma in-process, health checks. DATA_MODEL: `demo_sessions`, `ai_spend_days`, `ai_spend_calls`, `ai_spend_visitors`, the new generation fields (`session_id`, `expires_at`, `is_example`, `example_key`), `usage` removed. WORKFLOW section 5: five jobs including `Leaked secrets (gitleaks)`, and that adding it as a required check is a GitHub setting (master plan Phase 0). CLAUDE.md: `docker compose up -d` starts Mongo only; `npm run seed` with the API stopped; the local production run command.

- [ ] **Step 5: Check the writing rules**

Run (macOS grep has no `-P`, so Perl does the Unicode match): `git diff --name-only dev... | xargs perl -CSD -ne 'print "$ARGV:$.: $_" if /\x{2014}/; close ARGV if eof'` and `git diff dev... -- . ':!docs/superpowers/plans' | grep -nE '^\+.*\b(colour|behaviour|organisation|cancelled|licence)\b'`
Expected: no output from either (identifiers such as Python's `CancelledError` don't match the lowercase pattern).

- [ ] **Step 6: Commit**

CHANGELOG: `### Docs: demo readiness decisions and a deploy reference`.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `docs: record the demo readiness decisions and the deploy reference`

---

### Task 18: Local production verification, handoff, and PR

**Files:**
- Modify: this plan (tick the boxes; record results under "Verification results" at the end), `/Users/jameslittlefield/Documents/github_things/portfolio-infra/PLAN.md` (Folio's row; and, if James approved D2, Phase 3 item 3's "Folio's production seed costs a few cents" line)

**Interfaces:** Consumes everything above. No paid calls: the budget is 0 and the Anthropic key is a placeholder.

- [ ] **Step 1: Build and start**

Stop `npm run dev` (it holds port 8000). In one shell for the whole task: `export JWT_SECRET_KEY=$(openssl rand -hex 32)` (compose needs it for every command, `logs` and `stop` included). Run: `docker compose -f docker-compose.prod.yml up -d --build`, then `docker compose -f docker-compose.prod.yml logs app | grep -i seed`
Expected: the app becomes `healthy`; the seed log lists what it created and no error.

- [ ] **Step 2: Liveness and readiness**

Run: `curl -s localhost:8000/api/health/live` and `curl -s localhost:8000/api/health`; then `docker compose -f docker-compose.prod.yml stop mongo`, `curl -s -o /dev/null -w '%{http_code} %{time_total}\n' localhost:8000/api/health` and the live probe; then `docker compose -f docker-compose.prod.yml start mongo` and readiness again.
Expected: live 200 throughout; readiness 200, then 503 in about 2 to 3 seconds with Mongo stopped, then 200 again; `docker inspect` shows the container stayed up.

- [ ] **Step 3: Headers, closed routes, and the image**

Run: `curl -sI localhost:8000/ | grep -iE 'content-security-policy|x-content-type|x-frame|strict-transport'`; `curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/auth/login -H 'content-type: application/json' -d '{"email":"demo@folio.studio","password":"demo-folio-2026"}'`; `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/docs/` then check the body is the SPA, not Swagger; the image secret scan from ci.yml:155-162 against `folio:local`.
Expected: the CSP has `script-src 'self' 'wasm-unsafe-eval' https://challenges.cloudflare.com` and `frame-src https://challenges.cloudflare.com`; nosniff, frame protection, and HSTS are present; login 404; no `.env` in the image.

- [ ] **Step 4: One-click demo, free path, and the budget refusal (browser)**

In a normal window and a private window, open `http://localhost:8000/`: the status notice says live generation is paused (budget 0) before any bot check; "See ready-made examples" opens `/examples` with four examples and a downloadable PDF without starting a demo; "Explore the studio" shows the test widget, starts a demo, and lands on the dashboard; History shows the four examples with badges and no delete or edit; a generation attempt shows `LIVE_AI_PAUSED_COPY` with the examples link; `docker compose -f docker-compose.prod.yml logs app` shows no request to Anthropic or OpenAI.

- [ ] **Step 5: Two visitors can't see or edit each other's work**

Take each window's token from localStorage (`folio-auth`). Insert one text generation for visitor A with `docker compose -f docker-compose.prod.yml exec mongo mongosh folio --eval '<insert with A's session_id, expires_at in the future, the demo workspace_id and owner_id>'` (read the IDs from an example document first). Then with curl and each token: A's list and count include it, B's don't; B's GET, PATCH, and DELETE on its ID are 404; PATCH and DELETE on an example are 403 for both; A's DELETE succeeds.

- [ ] **Step 6: A forged X-Forwarded-For does not change the rate-limit key**

Restart the app with `DEMO_STARTS_PER_HOUR=2`. From inside the container (peer 127.0.0.1, a trusted proxy here, standing in for the ALB) run a short `python -` script with `urllib` that posts three demo starts with `{"turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"}` and `X-Forwarded-For: <random>, 203.0.113.9` (a different forged leftmost entry each time), then one with `X-Forwarded-For: 203.0.113.10`.
Expected: 200, 200, 429, then 200.

- [ ] **Step 7: Keep-alive and graceful stop**

Run a `python3` script on the host with `http.client.HTTPConnection("localhost", 8000)`: one request, `time.sleep(125)`, a second request on the same connection. Then `time docker compose -f docker-compose.prod.yml stop app`.
Expected: the second request succeeds (the server held the connection past the ALB's 120 s); the stop takes under 30 s.

- [ ] **Step 8: Data survives a restart; memory fits**

Don't open Chroma from a second process to count it (`docker compose exec app python ...` would be one); readiness and the seed report cover it. Record the example PDF's checksum: `docker compose -f docker-compose.prod.yml exec app sh -c 'sha256sum /app/storage/*/documents/*/document.pdf'`. Run `docker compose -f docker-compose.prod.yml restart app`, then `down` and `up -d` (volumes kept).
Expected: after each, readiness is 200, the seed log says nothing was repaired, and the checksum is unchanged. Then `docker stats --no-stream` after browsing every page and downloading the examples: memory under 1024 MiB; record idle and peak. If `--read-only` broke anything (for example a library cache under `$HOME`), record the path and the fix (a tmpfs or `HOME=/tmp`) in `docs/DEPLOY.md`.

- [ ] **Step 9: Clean up and record**

Run `docker compose -f docker-compose.prod.yml down -v` (local volumes only). Fill in "Verification results" below (each check: pass or the finding, memory numbers, the read-only result). Commit the plan update.
Stop: show the diff summary and the proposed commit message, and wait for James's explicit OK before committing.
Message: `docs: record the local production verification`

- [ ] **Step 10: Review gate, then push and PR (docs/WORKFLOW.md section 5, tier 2: auth, secrets, isolation)**

Run `/code-review high` and `/security-review` (full) on `git diff dev...feat/portfolio-demo-readiness`; fix or consciously accept each finding (any fix is its own commit, with the same stop).
Stop: ask James for OK to push `feat/portfolio-demo-readiness` to origin. Then `git push -u origin feat/portfolio-demo-readiness`.
Stop: show the PR title and body (summary, the review outcomes, the verification results, and the decisions D1 to D6 as James settled them), and wait for James's OK before `gh pr create --base dev`. Wait for CI (including gitleaks, Task 16 Step 5).
Stop: ask James for OK to merge with a merge commit. The `dev` to `main` release is Phase 3.

- [ ] **Step 11: Update the master plan**

In `portfolio-infra/PLAN.md`, set Folio's row to "Local readiness verified; PR #<n> into dev" with the date, and, if D2 was approved, change Phase 3 item 3 to say Folio's seed is free.
Stop: show the diff and the proposed commit message in `portfolio-infra`, and wait for James's explicit OK before committing.

---

## Verification results

(Filled in during Task 18.)

---

## Deferred to Phase 2/3 (AWS)

- CDK stacks (instance, data volume, ALB, WAF, cluster, services, roles) in `portfolio-infra`.
- ECR repository and image pushes.
- ECS task definitions for the Folio service and the hourly cleanup task (reference below).
- The deploy workflow (build, push, register, update, smoke tests) in this repo.
- GitHub OIDC deploy role and the `production` environment.
- Real Turnstile keys for `folio.jameslittlefield.net` (SSM).
- `FORWARDED_ALLOW_IPS` set to the VPC CIDR, and `APP_ORIGIN=https://folio.jameslittlefield.net`.
- DNS failover pair, the fallback site, WAF rules (Folio's expensive paths: generate, template AI, brand extract, demo start).
- Go-live checks on AWS (5.9 and 5.10), including the cross-visitor test with real generations and the failover drill.
- GitHub repository settings for Folio: secret scanning, push protection, Dependabot security updates, the gitleaks check as required (master plan Phase 0).
- The production seed against Atlas: free with D2 approved (it runs at startup); otherwise a paid run of a few cents with James's OK.
- Unsplash production access (James's action).
- The `origin/dev` to `main` release merge (Phase 3, James's OK).
- Anthropic Folio workspace ($12 limit) and the OpenAI project limit (Phase 2, outside AWS).

### ECS reference for Phase 2 (copy into the task definitions)

**Service `folio`** (one task; deployment minimum 0% and maximum 100%, stop then start; never two tasks: Chroma is in-process)

| Setting | Value |
|---|---|
| Image | the Folio ECR image (amd64) |
| Command | the image's CMD: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --timeout-keep-alive 130 --timeout-graceful-shutdown 25` (no ENTRYPOINT, so an ECS `command` override works) |
| User | 10001 (from the image) |
| Port | 8000, bridge mode, dynamic host port |
| Health check (container) | `["CMD", "python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3).status == 200 else 1)"]`, interval 30 s, timeout 5 s, retries 3, start period 60 s |
| ALB target health check | `GET /api/health/live`, expect 200 |
| Smoke test (deploy) | `GET /` 200, `GET /api/health` 200, `POST /api/auth/login` 404 |
| Volumes | host `/data/folio/storage` to `/app/storage`; host `/data/folio/chroma` to `/app/chroma`; both owned by 10001:10001 on the host (the app refuses to start otherwise) |
| Root filesystem | read-only if Task 18 confirmed it, with a tmpfs at `/tmp` |
| Linux | drop all capabilities, `no-new-privileges`, not privileged |
| Stop timeout | 30 s |
| Memory | reservation 512 MiB, hard limit 1024 MiB |
| Plain env | `APP_ORIGIN=https://folio.jameslittlefield.net`, `CORS_ORIGINS=["https://folio.jameslittlefield.net"]`, `DATABASE_NAME=folio`, `FORWARDED_ALLOW_IPS=<VPC CIDR>`, `AI_MONTHLY_BUDGET_USD=10`, `AI_PACING_MULTIPLIER=3`, `AI_DAILY_FLOOR_USD=0.50`, `AI_VISITOR_BUDGET_USD=0.15`, `DEMO_STARTS_PER_HOUR=15`, `DEMO_STARTS_PER_DAY=50`, `TURNSTILE_SITE_KEY=<real site key>` (image defaults: `ENVIRONMENT=production`, `SEED_ON_STARTUP=true`, `STORAGE_LOCAL_DIR=/app/storage`, `CHROMA_PATH=/app/chroma`) |
| Secrets (SSM `/portfolio/folio/*`) | `MONGODB_URL` (Atlas URI naming the `folio` database), `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY` (Folio workspace), `OPENAI_API_KEY` (Folio project), `UNSPLASH_ACCESS_KEY`, `TURNSTILE_SECRET_KEY` |

**Scheduled task `folio-cleanup`** (EventBridge Scheduler, hourly)

| Setting | Value |
|---|---|
| Image | the same image |
| Command override | `["python", "-m", "app.jobs.cleanup"]` |
| Volumes | host `/data/folio/storage` to `/app/storage` only (it never opens Chroma; a test guards that) |
| Env | `DATABASE_NAME=folio`; secrets `MONGODB_URL`, `JWT_SECRET_KEY` (the settings module checks it at import in production) |
| Memory | 128 MiB |
| Exit code | non-zero on any failure (drives the "scheduled task failed" alarm) |
| Does | charges reservations open longer than 10 minutes; deletes expired visitor work (files first, then records), expired sessions, and their visitor allowances; prunes settled ledger call records older than 35 days (day totals are kept) |
