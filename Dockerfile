# Multi-stage production image (deployment is deferred — see docs/PLAN.md).
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

# Run unprivileged. STORAGE_LOCAL_DIR defaults to ./storage, so it must be
# writable by the runtime user.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/storage \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENV ENVIRONMENT=production
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
