# Multi-stage Dockerfile for Portfolio Manager Service
# Position tracking and P&L calculations
# Port: 8003

# ============================================================================
# Stage 1: Builder - Compile dependencies
# ============================================================================
FROM python:3.12-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY requirements.txt .

# Create empty shared requirements file (will be overwritten if shared exists)
RUN echo "# No shared requirements" > shared-requirements.txt

# Install dependencies
# Make pip resilient on slow networks (audit 2026-04-29).
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.12-slim

LABEL maintainer="crypto-trading-bot"
LABEL service="portfolio-manager"
LABEL version="1.0.0"
LABEL description="Portfolio Management Service"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    SERVICE_NAME=portfolio-manager \
    SERVICE_PORT=8003 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Create shared directory
RUN mkdir -p ./shared

# Copy application code
COPY --chown=appuser:appuser app/ ./app/

# Create necessary directories
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "2"]
