# ============================================================================
# REIT Sheet - Simple HTTP Scraper Lambda
# ============================================================================
# Handles 90% of companies using lightweight HTTP clients
# Cost: ~$0.001 per invocation (256MB, 5-10s avg)

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "simple_scraper" {
  filename         = "${path.module}/../lambdas/simple-scraper.zip"
  source_code_hash = fileexists("${path.module}/../lambdas/simple-scraper.zip") ? filebase64sha256("${path.module}/../lambdas/simple-scraper.zip") : null
  function_name    = "${var.project_name}-simple-scraper"
  role             = aws_iam_role.simple_scraper.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  description      = "Lightweight HTTP scraper - handles standard press release pages without JavaScript"

  timeout     = 60  # 1 minute (fast scraping)
  memory_size = 256 # Low memory (lightweight)

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      LOG_LEVEL       = "INFO"
    }
  }

  tags = merge(local.lambda_tags, {
    Name      = "${var.project_name}-simple-scraper"
    Purpose   = "simple-http-scraping"
    Cost      = "low"
    Memory    = "256MB"
    Timeout   = "60s"
    Companies = "90-percent"
    Methods   = "curl-cffi-cloudscraper"
  })
}

# -----------------------------------------------------------------------------
# SQS Event Source Mapping
# -----------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "simple_scraper" {
  event_source_arn = aws_sqs_queue.simple_scraper.arn
  function_name    = aws_lambda_function.simple_scraper.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [
    aws_iam_role_policy.simple_scraper_sqs,
    aws_lambda_function.simple_scraper
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "simple_scraper" {
  name              = "/aws/lambda/${var.project_name}-simple-scraper"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name    = "simple-scraper-logs"
    Lambda  = "${var.project_name}-simple-scraper"
    LogType = "lambda-execution"
  })
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "simple_scraper" {
  name = "${var.project_name}-simple-scraper-role"

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
    Name    = "${var.project_name}-simple-scraper-role"
    Purpose = "lambda-execution-role"
  })
}

# -----------------------------------------------------------------------------
# IAM Policies
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "simple_scraper_basic" {
  role       = aws_iam_role.simple_scraper.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "simple_scraper_dynamodb" {
  name = "${var.project_name}-simple-scraper-dynamodb"
  role = aws_iam_role.simple_scraper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
      Resource = aws_dynamodb_table.reit_news_v2.arn
    }]
  })
}

resource "aws_iam_role_policy" "simple_scraper_sqs" {
  name = "${var.project_name}-simple-scraper-sqs"
  role = aws_iam_role.simple_scraper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ]
      Resource = aws_sqs_queue.simple_scraper.arn
    }]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "simple_scraper_function_name" {
  description = "Simple scraper Lambda function name"
  value       = aws_lambda_function.simple_scraper.function_name
}

output "simple_scraper_function_arn" {
  description = "Simple scraper Lambda function ARN"
  value       = aws_lambda_function.simple_scraper.arn
}
