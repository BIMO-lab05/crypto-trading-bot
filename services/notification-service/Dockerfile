# Multi-stage Dockerfile for Notification Service
# Alerts and notification management
# Port: 8006

# ============================================================================
# Stage 1: Builder - Compile dependencies
# ============================================================================
FROM python:3.14-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.14-slim

LABEL maintainer="crypto-trading-bot"
LABEL service="notification-service"
LABEL version="1.0.0"
LABEL description="Notification and Alert Service"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    SERVICE_NAME=notification-service \
    SERVICE_PORT=8006

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser app/ ./app/

# Create necessary directories
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

EXPOSE 8006

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006", "--workers", "1"]
