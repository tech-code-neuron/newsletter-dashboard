# ============================================================================
# Brave News Fetcher Lambda
# ============================================================================
# Searches Brave API daily for private company press releases from PR newswires.
# Results >= 75% confidence go to reit-news-v2 table.
# Results < 75% confidence go to manual-review table for human review.
#
# Triggered by EventBridge at 8:30 AM ET daily

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "brave_news_fetcher" {
  filename      = "../lambdas/brave-news-fetcher.zip"
  function_name = "${var.project_name}-brave-news-fetcher"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = 300
  memory_size   = 256
  description   = "Fetches private company press releases from Brave Search API"

  source_code_hash = fileexists("../lambdas/brave-news-fetcher.zip") ? filebase64sha256("../lambdas/brave-news-fetcher.zip") : null

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      COMPANIES_TABLE      = aws_dynamodb_table.companies_config.name
      REIT_NEWS_TABLE      = aws_dynamodb_table.reit_news_v2.name
      MANUAL_REVIEW_TABLE  = aws_dynamodb_table.manual_review.name
      CONFIDENCE_THRESHOLD = "75"
      LOG_LEVEL            = "INFO"
      SUMMARY_TO           = var.email_forward_destination
      SUMMARY_FROM         = "alerts@${var.domain_name}"
    }
  }

  tags = merge(local.lambda_tags, {
    Name        = "REIT-Sheet-Brave-News-Fetcher-Lambda"
    Description = "Fetches-private-company-press-releases-from-Brave-API"
    Function    = "brave-news-fetcher"
    Trigger     = "eventbridge"
  })

  depends_on = [
    aws_cloudwatch_log_group.brave_news_fetcher_logs
  ]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "brave_news_fetcher_logs" {
  name              = "/aws/lambda/${var.project_name}-brave-news-fetcher"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Brave-News-Fetcher-Logs"
  })
}

# -----------------------------------------------------------------------------
# EventBridge - Trigger at 8:30 AM ET Weekdays Only
# -----------------------------------------------------------------------------
# Note: 12:30 UTC = 8:30 AM EDT, 7:30 AM EST
# Using 12:30 UTC which is 8:30 AM during Eastern Daylight Time
# Weekdays only - Monday search covers Friday-Monday (weekend catch-up)

resource "aws_cloudwatch_event_rule" "brave_news_fetcher_schedule" {
  name                = "${var.project_name}-brave-news-fetcher-schedule"
  description         = "Trigger Brave news fetcher at 8:05 AM ET weekdays (12:05 UTC during EDT)"
  schedule_expression = "cron(5 12 ? * MON-FRI *)"

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Brave-News-Fetcher-Schedule"
  })
}

resource "aws_cloudwatch_event_target" "brave_news_fetcher_lambda" {
  rule      = aws_cloudwatch_event_rule.brave_news_fetcher_schedule.name
  target_id = "BraveNewsFetcherLambda"
  arn       = aws_lambda_function.brave_news_fetcher.arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_brave_news_fetcher" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.brave_news_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.brave_news_fetcher_schedule.arn
}

# -----------------------------------------------------------------------------
# IAM - Brave News Fetcher Permissions
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "brave_news_fetcher_dynamodb" {
  name = "${var.project_name}-brave-news-fetcher-dynamodb"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadCompaniesConfig"
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.companies_config.arn
      },
      {
        Sid    = "DynamoDBWriteReitNews"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.reit_news_v2.arn
      },
      {
        Sid    = "DynamoDBWriteManualReview"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.manual_review.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "brave_news_fetcher_secrets" {
  name = "${var.project_name}-brave-news-fetcher-secrets"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerReadBraveApiKey"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:reitsheet/brave-search-api-key*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "brave_news_fetcher_cloudwatch" {
  name = "${var.project_name}-brave-news-fetcher-cloudwatch"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchPutMetrics"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "ReitSheet/BraveNewsFetcher"
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarms
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "brave_api_errors" {
  alarm_name          = "${var.project_name}-brave-api-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "BraveSearchAPIErrors"
  namespace           = "ReitSheet/BraveNewsFetcher"
  period              = 86400  # 24 hours
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Brave Search API error rate exceeded 5 errors in 24 hours"
  treat_missing_data  = "notBreaching"

  alarm_actions = []  # Add SNS topic ARN if notifications desired

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Brave-API-Errors-Alarm"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "brave_news_fetcher_function_name" {
  description = "Brave news fetcher Lambda function name"
  value       = aws_lambda_function.brave_news_fetcher.function_name
}

output "brave_news_fetcher_schedule" {
  description = "Brave news fetcher cron schedule (UTC)"
  value       = aws_cloudwatch_event_rule.brave_news_fetcher_schedule.schedule_expression
}

output "manual_trigger_brave_fetcher_command" {
  description = "Command to manually trigger brave news fetcher"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.brave_news_fetcher.function_name} --payload '{\"search_date\": \"2026-03-31\"}' /tmp/brave-output.json && cat /tmp/brave-output.json"
}
