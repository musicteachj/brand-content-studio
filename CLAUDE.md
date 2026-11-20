# Folio (brand-content-studio)

Folio is one of James Littlefield's portfolio apps: a retrieval-augmented studio that writes on-brand LinkedIn posts, image cards, and documents. A FastAPI server (`server/`: MongoDB through Motor, in-process Chroma for vectors, OpenAI embeddings, Claude Sonnet 5.5 streamed over SSE) serves a React 19 + Vite client (`client/`). The public demo has no accounts: one click starts a private, temporary visitor session.

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
