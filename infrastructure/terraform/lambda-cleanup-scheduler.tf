# Lambda function for automated database cleanup
# Runs daily to remove bad URLs and duplicates

# Package Lambda deployment
data "archive_file" "cleanup_scheduler" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/cleanup-scheduler"
  output_path = "${path.module}/../lambdas/cleanup-scheduler.zip"
  excludes    = ["*.zip", "__pycache__", "*.pyc"]
}

# Lambda function
resource "aws_lambda_function" "cleanup_scheduler" {
  filename         = data.archive_file.cleanup_scheduler.output_path
  function_name    = "reitsheet-cleanup-scheduler"
  role             = aws_iam_role.cleanup_scheduler.arn
  handler          = "handler.handler"
  source_code_hash = data.archive_file.cleanup_scheduler.output_base64sha256
  runtime          = "python3.11"
  timeout          = 300 # 5 minutes (scanning can take time)
  memory_size      = 512
  description      = "Daily cleanup - removes bad URLs and duplicates from press release database"

  environment {
    variables = {
      REIT_NEWS_TABLE = aws_dynamodb_table.reit_news_v2.name
    }
  }

  tags = {
    Project = "reitsheet"
    Purpose = "automated_cleanup"
  }
}

# IAM role for cleanup Lambda
resource "aws_iam_role" "cleanup_scheduler" {
  name = "reitsheet-cleanup-scheduler-role"

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
    Purpose = "automated_cleanup"
  }
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "cleanup_scheduler_logs" {
  role       = aws_iam_role.cleanup_scheduler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access policy
resource "aws_iam_role_policy" "cleanup_scheduler_dynamodb" {
  name = "cleanup_scheduler_dynamodb"
  role = aws_iam_role.cleanup_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn
        ]
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "cleanup_scheduler" {
  name              = "/aws/lambda/reitsheet-cleanup-scheduler"
  retention_in_days = var.log_retention_days

  tags = {
    Project = "reitsheet"
    Purpose = "automated_cleanup"
  }
}

# EventBridge rule to trigger cleanup daily at 2 AM EST (7 AM UTC)
resource "aws_cloudwatch_event_rule" "cleanup_schedule" {
  name                = "reitsheet-cleanup-schedule"
  description         = "Trigger daily cleanup of bad URLs and duplicates"
  schedule_expression = "cron(0 7 * * ? *)"  # 7 AM UTC = 2 AM EST

  tags = {
    Project = "reitsheet"
    Purpose = "automated_cleanup"
  }
}

# EventBridge target to invoke Lambda
resource "aws_cloudwatch_event_target" "cleanup_lambda" {
  rule      = aws_cloudwatch_event_rule.cleanup_schedule.name
  target_id = "CleanupSchedulerLambda"
  arn       = aws_lambda_function.cleanup_scheduler.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge_cleanup" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cleanup_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cleanup_schedule.arn
}
