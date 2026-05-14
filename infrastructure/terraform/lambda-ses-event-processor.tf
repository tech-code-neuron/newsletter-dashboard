# ============================================================================
# REIT Sheet - SES Event Processor Lambda
# ============================================================================
# Processes email events from SNS (Send, Delivery, Bounce, Complaint, Open, Click)
# and updates DynamoDB tables for analytics and subscriber management.
#
# Tables Updated:
#   - reitsheet-email-events: Immutable event log (append-only)
#   - reitsheet-campaigns: Aggregate metrics (atomic increments)
#   - reitsheet-subscriber-engagement: Per-subscriber stats
#   - reitsheet-subscribers: Status updates (bounced/complained)
#
# Triggered by: SNS Topic (reitsheet-email-events)
#
# SOLID Principles:
#   - Single Responsibility: Processes SES events only
#   - Open/Closed: Add event types without modifying core logic

# -----------------------------------------------------------------------------
# SES Event Processor Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "ses_event_processor" {
  filename      = "${path.module}/../lambdas/ses-event-processor/ses-event-processor.zip"
  function_name = "${var.project_name}-ses-event-processor"
  role          = aws_iam_role.ses_event_processor_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = 30  # Short timeout - events are processed quickly
  memory_size   = 256
  description   = "Processes SES email events from SNS and updates DynamoDB tables"

  source_code_hash = fileexists("${path.module}/../lambdas/ses-event-processor/ses-event-processor.zip") ? filebase64sha256("${path.module}/../lambdas/ses-event-processor/ses-event-processor.zip") : null

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      EMAIL_EVENTS_TABLE          = aws_dynamodb_table.email_events.name
      CAMPAIGNS_TABLE             = aws_dynamodb_table.campaigns.name
      SUBSCRIBER_ENGAGEMENT_TABLE = aws_dynamodb_table.subscriber_engagement.name
      SUBSCRIBERS_TABLE           = aws_dynamodb_table.subscribers.name
      LOG_LEVEL                   = "INFO"
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-SES-Event-Processor"
    Description    = "Processes SES email events from SNS"
    Function       = "ses-event-processing"
    Trigger        = "sns"
    Downstream     = "dynamodb"
    ProcessingTime = "approx-100ms"
    Criticality    = "high"
  })

  depends_on = [
    aws_cloudwatch_log_group.ses_event_processor_logs
  ]
}

# -----------------------------------------------------------------------------
# SES Event Processor Lambda - IAM Role
# -----------------------------------------------------------------------------
# Separate role following least privilege principle

resource "aws_iam_role" "ses_event_processor_role" {
  name        = "${var.project_name}-ses-event-processor-role"
  description = "Execution role for SES Event Processor Lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name        = "REIT-Sheet-SES-Event-Processor-Role"
    Description = "IAM-role-for-SES-event-processor-Lambda"
    RoleType    = "service-role"
    AssignedTo  = "ses-event-processor-lambda"
    Principle   = "least-privilege"
  })
}

# -----------------------------------------------------------------------------
# SES Event Processor Lambda - IAM Policy
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "ses_event_processor_policy" {
  name = "${var.project_name}-ses-event-processor-policy"
  role = aws_iam_role.ses_event_processor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs - Required for Lambda logging
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-ses-event-processor:*"
      },

      # DynamoDB - Email Events table (write-only, immutable log)
      {
        Sid    = "DynamoDBEmailEventsAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.email_events.arn
      },

      # DynamoDB - Campaigns table (read/update for atomic increments)
      {
        Sid    = "DynamoDBCampaignsAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.campaigns.arn
      },

      # DynamoDB - Subscriber Engagement table (read/update for metrics)
      {
        Sid    = "DynamoDBSubscriberEngagementAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.subscriber_engagement.arn
      },

      # DynamoDB - Subscribers table (update status on bounce/complaint)
      {
        Sid    = "DynamoDBSubscribersAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.subscribers.arn
      },

      # X-Ray - Distributed tracing
      {
        Sid    = "XRayTracingAccess"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# SNS Subscription - Connect SNS Topic to Lambda
# -----------------------------------------------------------------------------

resource "aws_sns_topic_subscription" "ses_events_to_lambda" {
  topic_arn = aws_sns_topic.email_events.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.ses_event_processor.arn
}

# -----------------------------------------------------------------------------
# Lambda Permission - Allow SNS to invoke Lambda
# -----------------------------------------------------------------------------

resource "aws_lambda_permission" "sns_invoke_ses_event_processor" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ses_event_processor.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.email_events.arn
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ses_event_processor_logs" {
  name              = "/aws/lambda/${var.project_name}-ses-event-processor"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name   = "SES-Event-Processor-Lambda-Logs"
    Lambda = "${var.project_name}-ses-event-processor"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarm - Lambda Errors
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "ses_event_processor_errors" {
  alarm_name          = "${var.project_name}-ses-event-processor-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert when SES event processor has errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.ses_event_processor.function_name
  }

  tags = merge(local.monitoring_tags, {
    Name     = "SES-Event-Processor-Errors-Alarm"
    Severity = "medium"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ses_event_processor_function_name" {
  description = "SES event processor Lambda function name"
  value       = aws_lambda_function.ses_event_processor.function_name
}

output "ses_event_processor_function_arn" {
  description = "SES event processor Lambda function ARN"
  value       = aws_lambda_function.ses_event_processor.arn
}
