# ============================================================================
# AWS X-Ray Tracing Configuration
# ============================================================================
# Enable distributed tracing across all Lambda functions
# Trace emails from S3 → Parser → Enricher → Scraper → DynamoDB
#
# SOLID Compliance:
#   - Single Responsibility: Only configures X-Ray tracing
#   - Open/Closed: Add new Lambdas without modifying existing config
#   - No Hardcoded Values: Mode extracted to local variable
#
# X-Ray Modes:
#   - Active: Trace all requests (recommended for production)
#   - PassThrough: Only trace if upstream sent trace ID
#
# Last Updated: 2026-03-09
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# X-Ray Configuration
# -----------------------------------------------------------------------------
# Centralized X-Ray settings for all Lambda functions

locals {
  xray_config = {
    mode = "Active" # Active or PassThrough
  }
}

# -----------------------------------------------------------------------------
# IAM Permissions for X-Ray
# -----------------------------------------------------------------------------
# Grant Lambda functions permission to write X-Ray traces

data "aws_iam_policy" "xray_write_only" {
  arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Main Lambda Role - X-Ray Permission
# Covers: producer, parser, scraper, enricher, email_forwarder, daily_summary
# (all use aws_iam_role.lambda_role)
resource "aws_iam_role_policy_attachment" "lambda_role_xray" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = data.aws_iam_policy.xray_write_only.arn
}

# Playwright Scraper Lambda - X-Ray Permission (uses separate role)
resource "aws_iam_role_policy_attachment" "playwright_scraper_xray" {
  role       = aws_iam_role.playwright_scraper.name
  policy_arn = data.aws_iam_policy.xray_write_only.arn
}

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
# X-Ray tracing is enabled by adding to each Lambda function resource:
#
#   tracing_config {
#     mode = local.xray_config.mode
#   }
#
# This is done in the individual Lambda .tf files:
#   - lambdas.tf (producer, parser, scraper)
#   - lambda-playwright-scraper.tf
#   - lambda-email-forwarder.tf
#   - lambda-daily-summary.tf
#
# After enabling, view traces in AWS Console:
#   https://console.aws.amazon.com/xray/home?region=us-east-1#/traces
