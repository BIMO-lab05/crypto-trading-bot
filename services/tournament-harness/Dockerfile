# Tournament Harness Service Dockerfile (Phase 3)
#
# Skeleton image for the Docker-isolated ML candidate evaluator. Build context
# is the service directory at this skeleton stage; 03-06 may flip context to
# the repo root so the orchestrator can COPY services/ml-retraining-service/app
# for the metrics-bridge import path. Adjust there, not here.
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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies. Make pip resilient on slow networks
# (audit 2026-04-29 — same pattern as ml-retraining-service Dockerfile).
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and SQL migrations.
# migrations/ is created in 03-03 (numbered SQL files); a .gitkeep placeholder
# at this stage keeps the COPY layer order stable so 03-03 can drop SQL files
# in without rewriting the Dockerfile.
COPY app/ ./app/
COPY migrations/ ./migrations/

# Tournament data dirs (bind-mounted from host in compose; created here so
# the container has the parents even when the host bind-mount is fresh).
RUN mkdir -p /app/data/leaderboard /app/data/results /app/data/snapshots

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose service port (verified free against the existing 12 services in
# docker-compose.unified.yml: 8000-8009 and 5432/5433/6379/15672/9090/3001/3000)
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8010/health')"

# Run the orchestrator/API. Per-experiment runners (03-03+) launch this same
# image with command=["python", "-m", "app.runner", ...] overriding CMD.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
