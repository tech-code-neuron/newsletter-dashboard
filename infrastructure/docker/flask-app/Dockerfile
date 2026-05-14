# ============================================================================
# REIT Newsletter Flask App - Docker Image
# ============================================================================
# Containerized Flask application for AWS ECS Fargate deployment
#
# NOTE: Playwright is NOT needed here - browser scraping is handled by
# the separate Playwright Scraper Lambda (infrastructure/lambdas/playwright-scraper)
#
# Build: Via CodeBuild (aws codebuild start-build --project-name reitsheet-flask-app-build)
# ============================================================================

# Use ECR Public Gallery to avoid Docker Hub rate limits
FROM public.ecr.aws/docker/library/python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=5001

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials for some Python packages
    gcc \
    libffi-dev \
    # Required by lxml
    libxml2-dev \
    libxslt-dev \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set working directory
WORKDIR /app

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies (excluding playwright - not needed for web UI)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn boto3

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data newsletters logs templates static \
    && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Run with gunicorn (production WSGI server)
# - 2 workers (adequate for 0.25 vCPU)
# - 4 threads per worker (handles concurrent requests)
# - Timeout 120s (matches Lambda medium timeout)
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
