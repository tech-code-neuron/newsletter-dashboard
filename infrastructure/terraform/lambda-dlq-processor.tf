# ============================================================================
# DLQ Processor Lambda
# ============================================================================
# Automatically retries failed messages from Dead Letter Queues
# Implements intelligent retry strategies and alerts on permanent failures
#
# SOLID Compliance:
#   - Single Responsibility: Only processes DLQ messages
#   - Strategy Pattern: Multiple retry strategies (backoff, fallback, manual)
#   - No Hardcoded Values: All config in environment variables
#
# Retry Strategies:
#   1. Exponential backoff (3 attempts)
#   2. Fallback scraper (Playwright → Simple)
#   3. Manual review table (permanent failures)
#   4. SNS alerts (on-call notification)
#
# Last Updated: 2026-03-09
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# DLQ Processor Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "dlq_processor" {
  filename      = "../lambdas/dlq-processor.zip"
  function_name = "${var.project_name}-dlq-processor"
  role          = aws_iam_role.dlq_processor.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = 300 # 5 minutes for retry processing
  memory_size   = 256

  source_code_hash = fileexists("../lambdas/dlq-processor.zip") ? filebase64sha256("../lambdas/dlq-processor.zip") : null

  description = "Processes messages from Dead Letter Queues with intelligent retry strategies"

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      PARSE_QUEUE_URL      = aws_sqs_queue.email_parse.url
      ENRICH_QUEUE_URL     = aws_sqs_queue.enrich.url
      SCRAPE_QUEUE_URL     = aws_sqs_queue.scrape.url
      PLAYWRIGHT_QUEUE_URL = aws_sqs_queue.playwright_scraper.url
      MANUAL_REVIEW_TABLE  = aws_dynamodb_table.manual_review.name
      ALERT_SNS_TOPIC      = aws_sns_topic.dlq_alerts.arn
      LOG_LEVEL            = "INFO"
      MAX_RETRY_ATTEMPTS   = "3"
      RETRY_BACKOFF_BASE   = "2"
    }
  }

  tags = merge(local.lambda_tags, {
    Name        = "REIT-Sheet-DLQ-Processor-Lambda"
    Description = "Processes-failed-messages-from-DLQs-with-intelligent-retry"
    Function    = "dlq-processing"
    Trigger     = "all-dlqs"
    Downstream  = "queues and manual-review"
    Criticality = "high"
  })

  depends_on = [
    aws_cloudwatch_log_group.dlq_processor_logs
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "dlq_processor_logs" {
  name              = "/aws/lambda/${var.project_name}-dlq-processor"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name   = "DLQ-Processor-Lambda-Logs"
    Lambda = "${var.project_name}-dlq-processor"
  })
}

# -----------------------------------------------------------------------------
# IAM Role for DLQ Processor
# -----------------------------------------------------------------------------

resource "aws_iam_role" "dlq_processor" {
  name        = "${var.project_name}-dlq-processor-role"
  description = "Execution role for DLQ processor Lambda with retry permissions"

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
    Name    = "${var.project_name}-dlq-processor-role"
    Purpose = "lambda-execution-role"
    Lambda  = "${var.project_name}-dlq-processor"
  })
}

# -----------------------------------------------------------------------------
# IAM Policy - CloudWatch Logs
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "dlq_processor_basic" {
  role       = aws_iam_role.dlq_processor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# -----------------------------------------------------------------------------
# IAM Policy - SQS Access (Read DLQs, Write to Queues)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "dlq_processor_sqs" {
  name = "${var.project_name}-dlq-processor-sqs"
  role = aws_iam_role.dlq_processor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Read from DLQs
      {
        Sid    = "DLQReadAccess"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = [
          aws_sqs_queue.email_parse_dlq.arn,
          aws_sqs_queue.enrich_dlq.arn,
          aws_sqs_queue.scrape_dlq.arn,
          aws_sqs_queue.playwright_scraper_dlq.arn
        ]
      },
      # Write to retry queues
      {
        Sid    = "RetryQueueWriteAccess"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          aws_sqs_queue.email_parse.arn,
          aws_sqs_queue.enrich.arn,
          aws_sqs_queue.scrape.arn,
          aws_sqs_queue.playwright_scraper.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM Policy - DynamoDB Access (Manual Review Table)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "dlq_processor_dynamodb" {
  name = "${var.project_name}-dlq-processor-dynamodb"
  role = aws_iam_role.dlq_processor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManualReviewTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.manual_review.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM Policy - SNS Access (Alerts)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "dlq_processor_sns" {
  name = "${var.project_name}-dlq-processor-sns"
  role = aws_iam_role.dlq_processor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SNSAlertPublish"
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.dlq_alerts.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Event Source Mappings - Trigger from All DLQs
# -----------------------------------------------------------------------------

# Parse DLQ
resource "aws_lambda_event_source_mapping" "dlq_processor_parse" {
  event_source_arn = aws_sqs_queue.email_parse_dlq.arn
  function_name    = aws_lambda_function.dlq_processor.arn
  batch_size       = 1 # Process one failure at a time
  enabled          = true

  depends_on = [
    aws_iam_role_policy.dlq_processor_sqs
  ]
}

# Enrich DLQ
# NOTE: Enricher failures are routed to Playwright queue (not back to enricher)
# to prevent recursive loops. The DLQ processor's send_to_playwright() handles this.
# See handler.py lines 179-212 for implementation.
resource "aws_lambda_event_source_mapping" "dlq_processor_enrich" {
  event_source_arn = aws_sqs_queue.enrich_dlq.arn
  function_name    = aws_lambda_function.dlq_processor.arn
  batch_size       = 1
  enabled          = true

  depends_on = [
    aws_iam_role_policy.dlq_processor_sqs
  ]
}

# Scrape DLQ
resource "aws_lambda_event_source_mapping" "dlq_processor_scrape" {
  event_source_arn = aws_sqs_queue.scrape_dlq.arn
  function_name    = aws_lambda_function.dlq_processor.arn
  batch_size       = 1
  enabled          = true

  depends_on = [
    aws_iam_role_policy.dlq_processor_sqs
  ]
}

# Playwright DLQ
resource "aws_lambda_event_source_mapping" "dlq_processor_playwright" {
  event_source_arn = aws_sqs_queue.playwright_scraper_dlq.arn
  function_name    = aws_lambda_function.dlq_processor.arn
  batch_size       = 1
  enabled          = true

  depends_on = [
    aws_iam_role_policy.dlq_processor_sqs
  ]
}

# -----------------------------------------------------------------------------
# Manual Review DynamoDB Table
# -----------------------------------------------------------------------------
# Stores permanently failed messages for manual investigation

resource "aws_dynamodb_table" "manual_review" {
  name         = "${var.project_name}-manual-review"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "saved_for_review_at"
    type = "S"
  }

  # GSI for querying by status
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "saved_for_review_at"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup of resolved items (30 days)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-manual-review"
    Purpose     = "failed-message-review"
    Description = "Stores-permanently-failed-messages-for-manual-investigation"
  })
}

# -----------------------------------------------------------------------------
# SNS Topic for DLQ Alerts
# -----------------------------------------------------------------------------
# Sends alerts to on-call engineer when messages fail permanently

resource "aws_sns_topic" "dlq_alerts" {
  name         = "${var.project_name}-dlq-alerts"
  display_name = "REIT Sheet DLQ Alerts"

  tags = merge(local.monitoring_tags, {
    Name    = "${var.project_name}-dlq-alerts"
    Purpose = "on-call-alerts"
  })
}

# Subscribe email to SNS topic
# NOTE: You must confirm the subscription via email after deployment
resource "aws_sns_topic_subscription" "dlq_alerts_email" {
  topic_arn = aws_sns_topic.dlq_alerts.arn
  protocol  = "email"
  endpoint  = var.email_forward_destination # Uses same email as forward destination
}

# -----------------------------------------------------------------------------
# CloudWatch Alarm - Manual Review Queue Depth
# -----------------------------------------------------------------------------
# Alert when manual review table gets too many items

resource "aws_cloudwatch_metric_alarm" "manual_review_high" {
  alarm_name          = "${var.project_name}-manual-review-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ConsumedWriteCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Alert when too many items added to manual review table"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.manual_review.name
  }

  alarm_actions = [aws_sns_topic.dlq_alerts.arn]

  tags = merge(local.monitoring_tags, {
    Name     = "Manual-Review-High-Alarm"
    Severity = "medium"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "dlq_processor_function_name" {
  value       = aws_lambda_function.dlq_processor.function_name
  description = "DLQ Processor Lambda function name"
}

output "manual_review_table_name" {
  value       = aws_dynamodb_table.manual_review.name
  description = "Manual review DynamoDB table name"
}

output "dlq_alerts_topic_arn" {
  value       = aws_sns_topic.dlq_alerts.arn
  description = "SNS topic ARN for DLQ alerts"
}
