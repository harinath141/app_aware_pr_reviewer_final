# --- Stage 1: build the React dashboard -------------------------------------------------------
# node:22-slim (glibc) rather than alpine (musl), so the platform-specific Rollup binary recorded
# in package-lock.json matches the host that generated it.
FROM node:22-slim AS frontend
WORKDIR /src/frontend
# Manifests first, so `npm ci` stays cached until the dependencies themselves change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts sets root=frontend/ and outDir=../app/static, so this writes /src/app/static.
RUN npm run build

# --- Stage 2: the application -----------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
# The built dashboard replaces app/static, so this must come after `COPY app ./app`.
COPY --from=frontend /src/app/static ./app/static
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
