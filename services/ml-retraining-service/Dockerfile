# ML Retraining Service Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies. Make pip resilient on slow networks (audit 2026-04-29).
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create a non-root user to run the service.
# SECURITY (2026-07-29 audit): this service previously ran as root (no
# USER directive), unlike every other service in the repo which drops to
# `appuser`. Running the container as root broadens the blast radius of any
# RCE/container-escape. Create the user and hand it ownership of the app
# and model-storage directories.
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create directories for model storage
RUN mkdir -p /app/models/production \
    /app/models/versions \
    /app/models/backups \
    && chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Drop privileges
USER appuser

# Expose service port
EXPOSE 8009

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8009/health')"

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
