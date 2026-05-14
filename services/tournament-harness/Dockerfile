# Tournament Harness Service Dockerfile (Phase 3)
#
# Build context: repo root (.) — changed in 03-06 so we can COPY
# services/ml-retraining-service/app for the metrics-bridge import path.
# Compose stanza sets:
#   build:
#     context: .
#     dockerfile: services/tournament-harness/Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for compiled wheels
# (numpy, pandas, asyncpg, tensorflow build deps)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching (paths relative to repo-root context)
COPY services/tournament-harness/requirements.txt .

# Install Python dependencies. Make pip resilient on slow networks
# (audit 2026-04-29 — same pattern as ml-retraining-service Dockerfile).
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and SQL migrations.
# migrations/ is created in 03-03 (numbered SQL files); a .gitkeep placeholder
# at this stage keeps the COPY layer order stable so 03-03 can drop SQL files
# in without rewriting the Dockerfile.
COPY services/tournament-harness/app/ ./app/
COPY services/tournament-harness/migrations/ ./migrations/

# Vendor ml-retraining-service app/ for shared imports (TOURN-07 — runner imports
# returns_metrics / sharpe_metrics / cpcv / cpcv_evaluation / stationary_features
# / models registry rather than re-implementing them).
COPY services/ml-retraining-service/app /opt/ml_retraining/app

# Tournament data dirs (bind-mounted from host in compose; created here so
# the container has the parents even when the host bind-mount is fresh).
RUN mkdir -p /app/data/leaderboard /app/data/results /app/data/snapshots

# Set environment variables.
# /app first — tournament-harness's own app/ wins over ml-retraining's on conflicts.
# /opt/ml_retraining resolves from app.core.models, app.core.returns_metrics,
# app.sharpe_metrics, app.cpcv, app.core.cpcv_evaluation, app.core.stationary_features.
ENV PYTHONPATH=/app:/opt/ml_retraining
ENV PYTHONUNBUFFERED=1

# Expose service port (verified free against the existing 12 services in
# docker-compose.unified.yml: 8000-8009 and 5432/5433/6379/15672/9090/3001/3000)
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8010/health')"

# Drop to non-root user for CWE-250 (execution with unnecessary privileges).
# The data dirs and /output are created as root above; chown so appuser can write.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /opt/ml_retraining
USER appuser

# Run the orchestrator/API. Per-experiment runners (03-03+) launch this same
# image with command=["python", "-m", "app.runner", ...] overriding CMD.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
