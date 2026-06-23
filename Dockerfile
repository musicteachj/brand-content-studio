# Multi-stage production image (deployment is deferred — see docs/PLAN.md).
# Stage 1: build the React/Vite SPA.
FROM node:20-alpine AS frontend-builder
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# Stage 2: Python backend serving the built SPA via StaticFiles.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
COPY --from=frontend-builder /app/dist ./dist
EXPOSE 8000
ENV ENVIRONMENT=production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
