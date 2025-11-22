FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Set PYTHONPATH to include /app for module imports
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY ./services/portfolio-manager/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules (for database, utils, etc.)
COPY ./shared/ ./

# Copy application code
COPY ./services/portfolio-manager/app/ ./app/

# Copy tests for in-container testing
COPY ./services/portfolio-manager/tests/ ./tests/

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8003/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
