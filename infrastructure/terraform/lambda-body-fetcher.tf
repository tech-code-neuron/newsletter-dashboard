# ============================================================================
# Body Fetcher Lambda
# ============================================================================
# Fetches body content for press releases marked body_needed.
# Triggered every 15 minutes by EventBridge.
# Only processes during 6:00-9:30 AM ET and 4:00-9:00 PM ET.

resource "aws_lambda_function" "body_fetcher" {
  filename         = "../lambdas/body-fetcher.zip"
  function_name    = "${var.project_name}-body-fetcher"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = 300 # 5 minutes
  memory_size      = 512
  description      = "Fetches body content for body_needed press releases"

  source_code_hash = fileexists("../lambdas/body-fetcher.zip") ? filebase64sha256("../lambdas/body-fetcher.zip") : null

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      LOG_LEVEL       = "INFO"
    }
  }

  tags = merge(local.lambda_tags, {
    Name     = "${var.project_name}-body-fetcher"
    Function = "body-fetcher"
    Trigger  = "eventbridge"
  })

  depends_on = [aws_cloudwatch_log_group.body_fetcher_logs]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "body_fetcher_logs" {
  name              = "/aws/lambda/${var.project_name}-body-fetcher"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name = "${var.project_name}-body-fetcher-logs"
  })
}

# EventBridge - Every 15 minutes
resource "aws_cloudwatch_event_rule" "body_fetcher_schedule" {
  name                = "${var.project_name}-body-fetcher-schedule"
  description         = "Trigger body fetcher every 15 minutes"
  schedule_expression = "rate(15 minutes)"

  tags = merge(local.monitoring_tags, {
    Name = "${var.project_name}-body-fetcher-schedule"
  })
}

resource "aws_cloudwatch_event_target" "body_fetcher_lambda" {
  rule      = aws_cloudwatch_event_rule.body_fetcher_schedule.name
  target_id = "BodyFetcherLambda"
  arn       = aws_lambda_function.body_fetcher.arn
}

resource "aws_lambda_permission" "allow_eventbridge_body_fetcher" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.body_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.body_fetcher_schedule.arn
}

# IAM - DynamoDB access (Query GSI + UpdateItem)
resource "aws_iam_role_policy" "body_fetcher_dynamodb" {
  name = "${var.project_name}-body-fetcher-dynamodb"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QueryGSI"
        Effect = "Allow"
        Action = ["dynamodb:Query"]
        Resource = "${aws_dynamodb_table.reit_news_v2.arn}/index/social_status-first_seen_at-index"
      },
      {
        Sid    = "UpdateItems"
        Effect = "Allow"
        Action = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.reit_news_v2.arn
      }
    ]
  })
}

# IAM - CloudWatch Metrics
resource "aws_iam_role_policy" "body_fetcher_cloudwatch" {
  name = "${var.project_name}-body-fetcher-cloudwatch"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "ReitSheet/BodyFetcher"
          }
        }
      }
    ]
  })
}

# CloudWatch Alarm - Body Unavailable > 10/day
resource "aws_cloudwatch_metric_alarm" "body_unavailable_alarm" {
  alarm_name          = "${var.project_name}-body-unavailable-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "BodyUnavailable"
  namespace           = "ReitSheet/BodyFetcher"
  period              = 86400 # 1 day
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "More than 10 body_unavailable items in 24 hours - investigate failing sources"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.lambda_critical_alerts.arn]

  tags = merge(local.monitoring_tags, {
    Name = "${var.project_name}-body-unavailable-alarm"
  })
}
