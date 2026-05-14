# ============================================================================
# Daily Email Summary Lambda
# ============================================================================
# Sends daily summary of email statistics to user's Outlook inbox
# Triggered by EventBridge at 6 PM EST daily
#
# SOLID Principles:
#   - Single Responsibility: Only sends summary emails
#   - Open/Closed: Easy to add new metrics via DynamoDB queries
#   - No Hardcoded Values: All config in environment variables

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "daily_summary" {
  filename      = "../lambdas/daily-summary.zip"
  function_name = "${var.project_name}-daily-summary"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = 60
  memory_size   = 256
  description   = "Sends daily email summary to Outlook at 6 PM"

  source_code_hash = filebase64sha256("../lambdas/daily-summary.zip")

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      EMAIL_STATS_TABLE = aws_dynamodb_table.email_stats.name
      SUMMARY_TO        = var.email_forward_destination
      SUMMARY_FROM      = "alerts@${var.domain_name}"
    }
  }

  tags = merge(local.lambda_tags, {
    Name        = "REIT-Sheet-Daily-Summary-Lambda"
    Description = "Sends-daily-email-statistics-summary"
    Function    = "daily-summary"
    Trigger     = "eventbridge"
  })

  depends_on = [
    aws_cloudwatch_log_group.daily_summary_logs
  ]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "daily_summary_logs" {
  name              = "/aws/lambda/${var.project_name}-daily-summary"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Daily-Summary-Logs"
  })
}

# -----------------------------------------------------------------------------
# EventBridge (CloudWatch Events) - Trigger at 6 PM EST Daily
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "daily_summary_schedule" {
  name                = "${var.project_name}-daily-summary-schedule"
  description         = "Trigger daily email summary at 6 PM EST"
  schedule_expression = var.daily_summary_schedule

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Daily-Summary-Schedule"
  })
}

resource "aws_cloudwatch_event_target" "daily_summary_lambda" {
  rule      = aws_cloudwatch_event_rule.daily_summary_schedule.name
  target_id = "DailySummaryLambda"
  arn       = aws_lambda_function.daily_summary.arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_daily_summary" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_summary.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_summary_schedule.arn
}

# -----------------------------------------------------------------------------
# IAM - DynamoDB Read Permission for Summary Lambda
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "lambda_email_stats_read" {
  name = "${var.project_name}-lambda-email-stats-read"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadEmailStats"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.email_stats.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# IAM - DynamoDB Write Permission for Email Forwarder
# -----------------------------------------------------------------------------
# Allow email forwarder to update email statistics

resource "aws_iam_role_policy" "lambda_email_stats_write" {
  name = "${var.project_name}-lambda-email-stats-write"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBWriteEmailStats"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.email_stats.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "daily_summary_function_name" {
  description = "Daily summary Lambda function name"
  value       = aws_lambda_function.daily_summary.function_name
}

output "daily_summary_schedule" {
  description = "Daily summary cron schedule"
  value       = aws_cloudwatch_event_rule.daily_summary_schedule.schedule_expression
}

output "manual_trigger_summary_command" {
  description = "Command to manually trigger daily summary (for testing)"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.daily_summary.function_name} --region ${var.aws_region} /tmp/summary-output.json && cat /tmp/summary-output.json"
}
