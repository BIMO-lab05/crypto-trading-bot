# Multi-stage Dockerfile for ML Prediction Service
# LSTM-based price forecasting
# Port: 8007

# ============================================================================
# Stage 1: Builder - Compile dependencies
# ============================================================================
FROM python:3.12-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies (TensorFlow/PyTorch require extensive compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.12-slim

LABEL maintainer="crypto-trading-bot"
LABEL service="ml-prediction-service"
LABEL version="1.0.0"
LABEL description="ML Price Prediction Service"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    SERVICE_NAME=ml-prediction-service \
    SERVICE_PORT=8007 \
    OMP_NUM_THREADS=2 \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /app

# Install runtime dependencies for ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libopenblas0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser app/ ./app/

# Create necessary directories for models and logs
RUN mkdir -p /app/models /app/logs /app/cache && chown -R appuser:appuser /app

USER appuser

EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007", "--workers", "1"]
