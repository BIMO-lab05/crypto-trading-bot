# Multi-stage Dockerfile for Technical Analysis Service
# Trading indicators and signal generation
# Port: 8004

# ============================================================================
# Stage 1: Builder - Compile dependencies
# ============================================================================
FROM python:3.12-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies (pandas, numpy require compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
# Make pip resilient on slow networks (audit 2026-04-29).
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.12-slim

LABEL maintainer="crypto-trading-bot"
LABEL service="technical-analysis"
LABEL version="1.0.0"
LABEL description="Technical Analysis Indicators Service"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    SERVICE_NAME=technical-analysis \
    SERVICE_PORT=8004

WORKDIR /app

# Install runtime dependencies for numpy/pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libopenblas0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser app/ ./app/

# Create necessary directories
RUN mkdir -p /app/logs /app/cache && chown -R appuser:appuser /app

USER appuser

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "2"]
