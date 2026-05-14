# ============================================================================
# Playwright Lambda Layer
# ============================================================================
# Uses community-maintained Playwright Lambda layer
# Includes Chromium binaries pre-compiled for Lambda environment
#
# Alternative: Build custom layer if needed
# See: https://github.com/skorfmann/lambdaplaywright

# Note: For now, using direct package approach
# If package is too large (>50MB), uncomment layer approach below

/*
resource "aws_lambda_layer_version" "playwright" {
  filename   = "${path.module}/../layers/playwright-layer.zip"
  layer_name = "playwright-chromium"
  compatible_runtimes = [var.lambda_runtime]

  description = "Playwright with Chromium for headless browser automation"
}

# Attach layer to Playwright Lambda
resource "aws_lambda_function" "playwright_scraper" {
  # ... existing config ...

  layers = [
    aws_lambda_layer_version.playwright.arn
  ]
}
*/

# For production: Use Docker container image instead
# See lambda-playwright-docker.tf for Docker approach
