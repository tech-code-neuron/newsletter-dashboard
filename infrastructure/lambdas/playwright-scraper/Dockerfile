# ============================================================================
# Playwright Scraper Lambda - Docker Container
# ============================================================================
# Uses Microsoft's official Playwright Python image (Ubuntu-based, GLIBC 2.31+)
# Fixes GLIBC_2.27 mismatch error from AWS Lambda base images

FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Install AWS Lambda Runtime Interface Client
RUN pip install --no-cache-dir awslambdaric boto3

# Copy requirements and install to /var/task
COPY requirements.txt /var/task/
RUN pip install --no-cache-dir -r /var/task/requirements.txt --target /var/task

# Copy handler code and all modules
COPY handler.py /var/task/
COPY matching/ /var/task/matching/
COPY persistence/ /var/task/persistence/
COPY browser/ /var/task/browser/

# Copy shared modules (both to shared/ for package imports AND to root for direct imports)
COPY shared/ /var/task/shared/
COPY shared/*.py /var/task/

# Set Lambda-specific environment variables
ENV HOME=/tmp
# Include system site-packages for Playwright (installed in Microsoft base image)
ENV PYTHONPATH=/var/task:/usr/local/lib/python3.11/site-packages
WORKDIR /var/task

# Validate imports (catches NameError, ImportError before deployment)
# Env vars needed because handler reads them at import time
RUN AWS_DEFAULT_REGION=us-east-1 \
    REIT_NEWS_TABLE=test \
    COMPANIES_TABLE=test \
    python3 -c "import handler; print('Handler import: OK')"

# Lambda runtime entry point
# Use python3 from PATH (works in Microsoft Playwright image)
ENTRYPOINT ["/usr/bin/python3", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
