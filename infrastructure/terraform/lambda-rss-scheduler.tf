# RSS Scheduler Lambda - Fetches RSS feeds on schedule
# For companies that don't send press release emails (e.g., STAG - only sends financial reports)
# Runs daily at 8:05 AM ET (12:05 UTC during EDT, 13:05 UTC during EST)

# Lambda function - uses pre-built ZIP with feedparser bundled
# Build with: cd infrastructure/lambdas/rss-scheduler && ./build.sh
resource "aws_lambda_function" "rss_scheduler" {
  filename         = "${path.module}/../lambdas/rss-scheduler/rss-scheduler.zip"
  function_name    = "reitsheet-rss-scheduler"
  role             = aws_iam_role.rss_scheduler.arn
  handler          = "handler.handler"
  source_code_hash = filebase64sha256("${path.module}/../lambdas/rss-scheduler/rss-scheduler.zip")
  runtime          = "python3.11"
  timeout          = 120
  memory_size      = 256
  description      = "Scheduled RSS fetcher for companies without press release emails"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
      COMPANIES_TABLE = aws_dynamodb_table.companies_config.name
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "rss_scheduler"
  }
}

# IAM role for RSS scheduler Lambda
resource "aws_iam_role" "rss_scheduler" {
  name = "reitsheet-rss-scheduler-role"

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

  tags = {
    Project = "reitsheet"
    Purpose = "rss_scheduler"
  }
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "rss_scheduler_logs" {
  role       = aws_iam_role.rss_scheduler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access policy
resource "aws_iam_role_policy" "rss_scheduler_dynamodb" {
  name = "rss_scheduler_dynamodb"
  role = aws_iam_role.rss_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn,
          aws_dynamodb_table.companies_config.arn
        ]
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "rss_scheduler" {
  name              = "/aws/lambda/reitsheet-rss-scheduler"
  retention_in_days = var.log_retention_days

  tags = {
    Project = "reitsheet"
    Purpose = "rss_scheduler"
  }
}

# EventBridge rule to trigger at 8:05 AM ET daily
# Using 12:05 UTC (EDT) - during EST it will be 7:05 AM local
resource "aws_cloudwatch_event_rule" "rss_schedule" {
  name                = "reitsheet-rss-schedule"
  description         = "Trigger RSS fetcher at 8:05 AM ET daily"
  schedule_expression = "cron(5 12 * * ? *)"

  tags = {
    Project = "reitsheet"
    Purpose = "rss_scheduler"
  }
}

# EventBridge target to invoke Lambda
resource "aws_cloudwatch_event_target" "rss_scheduler_lambda" {
  rule      = aws_cloudwatch_event_rule.rss_schedule.name
  target_id = "RssSchedulerLambda"
  arn       = aws_lambda_function.rss_scheduler.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_rss" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rss_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.rss_schedule.arn
}
