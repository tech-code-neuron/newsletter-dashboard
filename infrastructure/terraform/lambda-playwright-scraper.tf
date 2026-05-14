# ============================================================================
# REIT Sheet - Playwright Scraper Lambda
# ============================================================================
# Scrapes JavaScript-rendered press releases (EPRT, etc.)
# Uses headless Chrome via Playwright to handle dynamic content
#
# Companies requiring JavaScript rendering:
#   - EPRT (Essential Properties) - SvelteKit framework
#
# SOLID Compliance:
#   - Single Responsibility: Only handles JS-rendered pages
#   - Open/Closed: Add companies via SCRAPER_CONFIG (no code changes)
#   - Extensible: Easy to add more JS-rendered companies

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
# Two deployment options:
#   1. ZIP file (simple, but limited to 250MB unzipped)
#   2. Docker container (recommended for Playwright, no size limit)
#
# For production: Use Docker approach (see Dockerfile)
# For testing: Can use ZIP with minimal package (will fail until Chromium added)

resource "aws_lambda_function" "playwright_scraper" {
  # -------------------------------------------------------------------------
  # Option 1: ZIP Deployment (disabled - Docker is production approach)
  # -------------------------------------------------------------------------
  # filename         = "${path.module}/../lambdas/playwright-scraper.zip"
  # source_code_hash = fileexists("${path.module}/../lambdas/playwright-scraper.zip") ? filebase64sha256("${path.module}/../lambdas/playwright-scraper.zip") : null
  # handler          = "handler.lambda_handler"
  # runtime          = var.lambda_runtime

  # -------------------------------------------------------------------------
  # Option 2: Docker Container (ACTIVE - fixes GLIBC mismatch)
  # -------------------------------------------------------------------------
  package_type = "Image"
  image_uri    = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/reitsheet-playwright-scraper:latest"
  description  = "Browser automation - scrapes JavaScript-rendered press releases using headless Chrome"

  function_name = local.playwright_scraper_function
  role          = aws_iam_role.playwright_scraper.arn
  timeout       = var.lambda_timeout_long # 5 minutes for browser startup + rendering
  memory_size   = 2048                    # 2GB required for Chrome + Playwright

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REIT_NEWS_TABLE         = aws_dynamodb_table.reit_news_v2.name
      COMPANIES_TABLE         = aws_dynamodb_table.companies_config.name
      LOG_LEVEL               = "INFO"
      MAX_MESSAGE_AGE_MINUTES = "60" # Longer for Playwright (slow browser startup)
    }
  }

  tags = merge(local.lambda_tags, {
    Name      = "reitsheet-playwright-scraper"
    Purpose   = "javascript-press-release-scraping"
    Runtime   = var.lambda_runtime
    Memory    = "2048MB"
    Timeout   = "${var.lambda_timeout_long}s"
    Companies = "EPRT"
  })
}

# -----------------------------------------------------------------------------
# SQS Event Source Mapping
# -----------------------------------------------------------------------------
# Triggers Lambda when messages arrive in Playwright queue

resource "aws_lambda_event_source_mapping" "playwright_scraper" {
  event_source_arn = aws_sqs_queue.playwright_scraper.arn
  function_name    = aws_lambda_function.playwright_scraper.arn
  batch_size       = var.sqs_batch_size # Process one at a time
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [
    aws_iam_role_policy.playwright_scraper_sqs,
    aws_lambda_function.playwright_scraper
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "playwright_scraper" {
  name              = "/aws/lambda/${local.playwright_scraper_function}"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name    = "playwright-scraper-logs"
    Lambda  = local.playwright_scraper_function
    LogType = "lambda-execution"
  })
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "playwright_scraper" {
  name = "${var.project_name}-playwright-scraper-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = merge(local.iam_tags, {
    Name    = "${var.project_name}-playwright-scraper-role"
    Purpose = "lambda-execution-role"
    Lambda  = local.playwright_scraper_function
  })
}

# -----------------------------------------------------------------------------
# IAM Policy - Basic Execution (CloudWatch Logs)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "playwright_scraper_basic" {
  role       = aws_iam_role.playwright_scraper.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# -----------------------------------------------------------------------------
# IAM Policy - DynamoDB Access
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "playwright_scraper_dynamodb" {
  name = "${var.project_name}-playwright-scraper-dynamodb"
  role = aws_iam_role.playwright_scraper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn,
          aws_dynamodb_table.companies_config.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM Policy - SQS Access
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "playwright_scraper_sqs" {
  name = "${var.project_name}-playwright-scraper-sqs"
  role = aws_iam_role.playwright_scraper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = aws_sqs_queue.playwright_scraper.arn
      }
    ]
  })
}
