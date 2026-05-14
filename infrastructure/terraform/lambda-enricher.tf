# ============================================================================
# REIT Sheet - URL Enricher Lambda
# ============================================================================
# Constructs and validates press release URLs
# Split from Parser Lambda for performance and SOLID compliance
#
# SOLID Principles:
# - Single Responsibility: Parser parses, Enricher enriches
# - Open/Closed: Add URL methods without modifying core logic
# - Strategy Pattern: URL construction methods

# -----------------------------------------------------------------------------
# Enricher Lambda Function
# -----------------------------------------------------------------------------
# Triggered by SQS enrichment queue messages
# Constructs URLs using company-specific methods
# Validates URLs with HTTP HEAD requests
# Routes: Valid URLs → DynamoDB, Invalid URLs → Scrape Queue

resource "aws_lambda_function" "enricher" {
  filename      = "${path.module}/../lambdas/enricher/enricher-latest.zip"
  function_name = "${var.project_name}-enricher"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_medium # 3 minutes (URL validation)
  memory_size   = 256                       # Low memory (no heavy processing)
  description   = "URL enricher - constructs and validates press release URLs using company-specific methods"

  source_code_hash = fileexists("${path.module}/../lambdas/enricher/enricher-latest.zip") ? filebase64sha256("${path.module}/../lambdas/enricher/enricher-latest.zip") : null

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      SCRAPE_QUEUE_URL          = aws_sqs_queue.scrape.url
      PLAYWRIGHT_QUEUE_URL      = aws_sqs_queue.playwright_scraper.url
      ENRICH_DLQ_URL            = aws_sqs_queue.enrich_dlq.url
      REIT_NEWS_TABLE           = aws_dynamodb_table.reit_news_v2.name
      COMPANIES_TABLE           = aws_dynamodb_table.companies_config.name
      SOCIAL_CLASSIFY_QUEUE_URL = aws_sqs_queue.social_classify.url
      LOG_LEVEL                 = "INFO"
      MAX_MESSAGE_AGE_MINUTES   = "30" # Stale message prevention (Phase 1)
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Enricher-Lambda"
    Description    = "Constructs-and-validates-press-release-URLs"
    Function       = "url-enrichment"
    Trigger        = "sqs-enrich-queue"
    Downstream     = "dynamodb and scrape-queue"
    ProcessingTime = "approx-5-15s"
    Criticality    = "high"
  })

  depends_on = [
    aws_cloudwatch_log_group.enricher_logs
  ]
}

# -----------------------------------------------------------------------------
# Enricher Lambda - SQS Trigger
# -----------------------------------------------------------------------------
# Event source mapping connects enrich queue to enricher Lambda

resource "aws_lambda_event_source_mapping" "enricher_trigger" {
  event_source_arn = aws_sqs_queue.enrich.arn
  function_name    = aws_lambda_function.enricher.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [
    aws_lambda_function.enricher,
    aws_sqs_queue.enrich
  ]
}

# -----------------------------------------------------------------------------
# Enricher Lambda - CloudWatch Log Group
# -----------------------------------------------------------------------------
# Stores Lambda execution logs

resource "aws_cloudwatch_log_group" "enricher_logs" {
  name              = "/aws/lambda/${var.project_name}-enricher"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name   = "Enricher-Lambda-Logs"
    Lambda = "${var.project_name}-enricher"
  })
}

# -----------------------------------------------------------------------------
# Enricher Lambda - CloudWatch Alarm (DLQ Depth)
# -----------------------------------------------------------------------------
# Alerts when enrichment jobs fail repeatedly

resource "aws_cloudwatch_metric_alarm" "enricher_dlq_alarm" {
  alarm_name          = "${var.project_name}-enricher-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "Alert when messages appear in Enricher DLQ"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.enrich_dlq.name
  }

  tags = merge(local.monitoring_tags, {
    Name     = "Enricher-DLQ-Alarm"
    Severity = "high"
  })
}
