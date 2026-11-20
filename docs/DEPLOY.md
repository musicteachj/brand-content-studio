# Deploying Folio

> How the production image runs, locally and on AWS. The decisions are DECISIONS #44 to #46; the infrastructure itself (CDK, ALB, WAF, DNS, the deploy workflow) lives in `../portfolio-infra` and the design `../portfolio-infra/docs/design/2026-11-18-portfolio-apps-aws-deployment-design.md`. This file holds what the Folio side must be configured with.
> Related: [DECISIONS.md](./DECISIONS.md) · [ARCHITECTURE.md](./ARCHITECTURE.md) · [WORKFLOW.md](./WORKFLOW.md)

---

## Run the production image locally

`docker-compose.prod.yml` runs the image the way production does: a read-only root filesystem with a `/tmp` tmpfs, no capabilities, `no-new-privileges`, a 1 GiB memory limit, and named volumes for Mongo, storage, and Chroma. Its project name is `folio-local`, so it never touches the development compose project. Live AI is off by default (`AI_MONTHLY_BUDGET_USD` defaults to 0), the Turnstile keys are Cloudflare's always-pass test keys (accepted only because `APP_ORIGIN` is a loopback origin), and no AI provider is called.

```bash
export JWT_SECRET_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d --build
```

Open http://localhost:8000. Stop it with `docker compose -f docker-compose.prod.yml down` (add `-v` to delete the volumes too).

## Reading the seed report

The image sets `SEED_ON_STARTUP=true`, so the API checks the demo seed after it ensures the indexes and logs one line:

```
Demo seed checked: created <list or "nothing">, repaired <list or "nothing">
```

On an empty database the first start lists what it built (the user, the Verdure workspace, the corpus, the examples); a later start on healthy data says `created nothing, repaired nothing`. A failure logs `The demo seed failed at startup` with the traceback and the app still starts. The same result is in readiness: `GET /api/health` returns `seed: true` when the seed is complete, `seed: false` after a failure (the response is then a 503), and `seed: null` when `SEED_ON_STARTUP` is off. The seed makes no paid call: vectors and examples come from the fixtures in `server/seed/fixtures/`.

## Restore

The data is Mongo (Atlas) plus two directories on the retained volume. To restore, attach the retained volume or a snapshot of it at `/data/folio`. Whatever is missing is rebuilt by the seed at the next start, at no cost: the corpus vectors and the ready-made examples come from the checked-in fixtures. Visitor work is removed after 24 hours anyway, so nothing a visitor made is worth restoring. Start the production database empty: the first start fills it.

## ECS reference

### Service `folio`

One task; deployment minimum 0% and maximum 100%, stop then start. Never two tasks: Chroma is in-process, and two copies must never share the data directory.

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
| Root filesystem | read-only, with a tmpfs at `/tmp` (see the go-live checklist) |
| Linux | drop all capabilities, `no-new-privileges`, not privileged |
| Stop timeout | 30 s |
| Memory | reservation 512 MiB, hard limit 1024 MiB |
| Plain env | `APP_ORIGIN=https://folio.jameslittlefield.net`, `CORS_ORIGINS=["https://folio.jameslittlefield.net"]`, `DATABASE_NAME=folio`, `FORWARDED_ALLOW_IPS=<VPC CIDR>`, `AI_MONTHLY_BUDGET_USD=10`, `AI_PACING_MULTIPLIER=3`, `AI_DAILY_FLOOR_USD=0.50`, `AI_VISITOR_BUDGET_USD=0.15`, `DEMO_STARTS_PER_HOUR=15`, `DEMO_STARTS_PER_DAY=50`, `TURNSTILE_SITE_KEY=<real site key>` (image defaults: `ENVIRONMENT=production`, `SEED_ON_STARTUP=true`, `STORAGE_LOCAL_DIR=/app/storage`, `CHROMA_PATH=/app/chroma`) |
| Secrets (SSM `/portfolio/folio/*`) | `MONGODB_URL` (Atlas URI naming the `folio` database), `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY` (Folio workspace), `OPENAI_API_KEY` (Folio project), `UNSPLASH_ACCESS_KEY`, `TURNSTILE_SECRET_KEY` |

### Scheduled task `folio-cleanup`

EventBridge Scheduler, hourly.

| Setting | Value |
|---|---|
| Image | the same image |
| Command override | `["python", "-m", "app.jobs.cleanup"]` |
| Volumes | host `/data/folio/storage` to `/app/storage` only (it never opens Chroma; a test guards that) |
| Env | `DATABASE_NAME=folio`; secrets `MONGODB_URL`, `JWT_SECRET_KEY` (the settings module checks it at import in production) |
| Memory | 128 MiB |
| Exit code | non-zero on any failure (drives the "scheduled task failed" alarm) |
| Does | charges reservations open longer than 10 minutes; deletes expired visitor work (files first, then records), expired sessions, and their visitor allowances; prunes settled ledger call records older than 35 days (day totals are kept) |

The job deletes visitor files strictly: a file that fails to delete keeps its record, and the job exits 1, so the next hour retries it.

## Go-live checklist

- [ ] `APP_ORIGIN` is the real https origin. Production accepts Turnstile test keys only when `APP_ORIGIN` is a loopback origin, so a wrong `APP_ORIGIN` could let the bot check pass with the public dummy token.
- [ ] `FORWARDED_ALLOW_IPS` is the VPC CIDR (never `*` or a `/0` network). A `docker run` of the image without it refuses to boot, by design.
- [ ] Exactly one Folio task runs, with stop-then-start deploys. Chroma is in-process, so two copies must never share the data directory.
- [ ] The task definition uses a read-only root filesystem with a `/tmp` tmpfs (defense in depth: the app code is already root-owned in the image, and CI boots the image read-only).
- [ ] The production database starts empty; the seed fills it at startup, for free.
- [ ] The Anthropic Folio workspace and the OpenAI project have their own spend limits, and real Turnstile keys are in SSM.
- [ ] After a deploy, the smoke tests pass: `GET /` 200, `GET /api/health` 200, `POST /api/auth/login` 404.
