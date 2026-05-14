# ============================================================================
# REIT Sheet - Scraper Router Lambda
# ============================================================================
# Routes scraping jobs to appropriate scraper based on company config
# SOLID: Strategy Pattern - Config-driven routing (no if-elif chains)

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "scraper_router" {
  filename         = "${path.module}/../lambdas/scraper-router.zip"
  source_code_hash = fileexists("${path.module}/../lambdas/scraper-router.zip") ? filebase64sha256("${path.module}/../lambdas/scraper-router.zip") : null
  function_name    = "${var.project_name}-scraper-router"
  role             = aws_iam_role.scraper_router.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  description      = "Routes scraping jobs to appropriate scraper based on company configuration"

  timeout     = 60  # 1 minute (just routing)
  memory_size = 256 # Low memory (no scraping)

  environment {
    variables = {
      SIMPLE_SCRAPER_QUEUE_URL = aws_sqs_queue.simple_scraper.url
      PLAYWRIGHT_QUEUE_URL     = aws_sqs_queue.playwright_scraper.url
      API_SCRAPER_QUEUE_URL    = "" # Not implemented yet
      COMPANIES_TABLE          = aws_dynamodb_table.companies_config.name
      LOG_LEVEL                = "INFO"
      CONFIG_CACHE_TTL_SECONDS = "300" # Company config cache TTL (5 minutes)
    }
  }

  tags = merge(local.lambda_tags, {
    Name    = "${var.project_name}-scraper-router"
    Purpose = "route-to-appropriate-scraper"
    Cost    = "very-low"
    Memory  = "256MB"
    Timeout = "60s"
    Pattern = "strategy-pattern-routing"
  })
}

# -----------------------------------------------------------------------------
# SQS Event Source Mapping
# -----------------------------------------------------------------------------
# Reads from the scrape queue (replaces old monolithic scraper)

resource "aws_lambda_event_source_mapping" "scraper_router" {
  event_source_arn = aws_sqs_queue.scrape.arn
  function_name    = aws_lambda_function.scraper_router.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [
    aws_iam_role_policy.scraper_router_sqs,
    aws_lambda_function.scraper_router
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "scraper_router" {
  name              = "/aws/lambda/${var.project_name}-scraper-router"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name    = "scraper-router-logs"
    Lambda  = "${var.project_name}-scraper-router"
    LogType = "lambda-execution"
  })
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "scraper_router" {
  name = "${var.project_name}-scraper-router-role"

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
    Name    = "${var.project_name}-scraper-router-role"
    Purpose = "lambda-execution-role"
  })
}

# -----------------------------------------------------------------------------
# IAM Policies
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "scraper_router_basic" {
  role       = aws_iam_role.scraper_router.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "scraper_router_dynamodb" {
  name = "${var.project_name}-scraper-router-dynamodb"
  role = aws_iam_role.scraper_router.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem"]
      Resource = aws_dynamodb_table.companies_config.arn
    }]
  })
}

resource "aws_iam_role_policy" "scraper_router_sqs" {
  name = "${var.project_name}-scraper-router-sqs"
  role = aws_iam_role.scraper_router.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read from scrape queue
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = aws_sqs_queue.scrape.arn
      },
      {
        # Send to simple scraper queue
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.simple_scraper.arn
      },
      {
        # Send to playwright queue
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.playwright_scraper.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "scraper_router_function_name" {
  description = "Scraper router Lambda function name"
  value       = aws_lambda_function.scraper_router.function_name
}

output "scraper_router_function_arn" {
  description = "Scraper router Lambda function ARN"
  value       = aws_lambda_function.scraper_router.arn
}
