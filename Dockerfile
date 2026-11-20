# Multi-stage production image. How it runs on AWS (ECS on EC2 behind an ALB) is in docs/DEPLOY.md.
# Stage 1: build the React/Vite SPA.
FROM node:24-alpine AS frontend-builder
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# Stage 2: Python backend serving the built SPA via StaticFiles.
FROM python:3.12-slim
WORKDIR /app

# No .pyc writes (the root filesystem may be read-only) and unbuffered logs. Uploads and
# rendered files live in /app/storage and Chroma's data in /app/chroma: mount a
# persistent volume at each. The self-healing demo seed runs at every start.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STORAGE_LOCAL_DIR=/app/storage CHROMA_PATH=/app/chroma SEED_ON_STARTUP=true DATABASE_NAME=folio

# gcc is only needed to build wheels; purge it so the runtime image ships no compiler.
COPY server/requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc \
    && rm -rf /var/lib/apt/lists/*

COPY server/ ./
# Vite's outDir is relative to stage 1's WORKDIR, so the build lands in
# /app/client/dist — not /app/dist.
COPY --from=frontend-builder /app/client/dist ./dist

# Run unprivileged as uid 10001. Only the two data directories belong to that uid; the
# app code stays root-owned, so the app can't rewrite itself even without a read-only
# root filesystem. A new named volume mounted on either directory starts with the same
# owner (Docker copies the directory's ownership into an empty volume). The app checks
# both are writable at startup and refuses to start, naming the directory, when one isn't.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/storage /app/chroma \
    && chown app:app /app/storage /app/chroma
USER app

EXPOSE 8000
ENV ENVIRONMENT=production
# Liveness only (no database): a Mongo outage must not get a running container
# restarted. The ALB target health check uses liveness too; readiness (/api/health,
# 503 when not ready) is for the deploy smoke tests. start-period covers the startup seed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3).status == 200 else 1)"
# Keep-alive stays above the ALB's 120 s idle timeout so the ALB never reuses a
# connection uvicorn already closed. Trusted proxies come from FORWARDED_ALLOW_IPS
# (an environment variable, validated at startup), never from a flag here.
# One worker, always: Chroma runs in-process, and only one process may open its
# directory (the in-memory rate limiter and caches assume one process too).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--timeout-keep-alive", "130", "--timeout-graceful-shutdown", "25"]
