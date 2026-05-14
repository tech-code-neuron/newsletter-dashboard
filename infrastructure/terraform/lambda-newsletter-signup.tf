# ============================================================================
# REIT Sheet - Newsletter Signup Lambda
# ============================================================================
# Handles newsletter subscription operations:
#   - POST /subscribe: Create subscriber and send verification email
#   - GET /verify/{token}: Verify email address
#   - GET /unsubscribe/{token}: Unsubscribe from newsletter
#
# Triggered by API Gateway HTTP API
#
# SOLID Principles:
#   - Single Responsibility: Handles only newsletter subscription logic
#   - Open/Closed: Easy to add new subscription features

# -----------------------------------------------------------------------------
# Newsletter Signup Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "newsletter_signup" {
  filename      = "${path.module}/../lambdas/newsletter-signup/newsletter-signup.zip"
  function_name = "${var.project_name}-newsletter-signup"
  role          = aws_iam_role.newsletter_signup_role.arn
  handler       = "handler.handler"
  runtime       = var.lambda_runtime
  timeout       = 30
  memory_size   = 256
  description   = "Newsletter signup - subscriber management and email verification"

  source_code_hash = fileexists("${path.module}/../lambdas/newsletter-signup/newsletter-signup.zip") ? filebase64sha256("${path.module}/../lambdas/newsletter-signup/newsletter-signup.zip") : null

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      SUBSCRIBERS_TABLE = aws_dynamodb_table.subscribers.name
      SES_SENDER_EMAIL  = "newsletter@${var.domain_name}"
      REPLY_TO_EMAIL    = "hello@${var.domain_name}"
      BASE_URL          = "https://${var.domain_name}"
      LOG_LEVEL         = "INFO"
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Newsletter-Signup-Lambda"
    Description    = "Newsletter-subscription-management"
    Function       = "newsletter-signup"
    Trigger        = "api-gateway"
    Downstream     = "dynamodb-ses"
    ProcessingTime = "approx-1-2s"
    Criticality    = "medium"
  })

  depends_on = [
    aws_cloudwatch_log_group.newsletter_signup_logs
  ]
}

# -----------------------------------------------------------------------------
# Newsletter Signup Lambda - IAM Role
# -----------------------------------------------------------------------------
# Separate role for newsletter signup to follow least privilege

resource "aws_iam_role" "newsletter_signup_role" {
  name        = "${var.project_name}-newsletter-signup-role"
  description = "Execution role for Newsletter Signup Lambda"

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
    Name        = "REIT-Sheet-Newsletter-Signup-Role"
    Description = "IAM-role-for-newsletter-signup-Lambda"
    RoleType    = "service-role"
    AssignedTo  = "newsletter-signup-lambda"
    Principle   = "least-privilege"
  })
}

# -----------------------------------------------------------------------------
# Newsletter Signup Lambda - IAM Policy
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "newsletter_signup_policy" {
  name = "${var.project_name}-newsletter-signup-policy"
  role = aws_iam_role.newsletter_signup_role.id

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
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-newsletter-signup:*"
      },

      # DynamoDB - Subscriber table access
      {
        Sid    = "DynamoDBSubscribersAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.subscribers.arn,
          "${aws_dynamodb_table.subscribers.arn}/index/*"
        ]
      },

      # SES - Send verification emails
      {
        Sid    = "SESSendEmailAccess"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ses:FromAddress" = "alerts@${var.domain_name}"
          }
        }
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
# Newsletter Signup Lambda - CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "newsletter_signup_logs" {
  name              = "/aws/lambda/${var.project_name}-newsletter-signup"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name   = "Newsletter-Signup-Lambda-Logs"
    Lambda = "${var.project_name}-newsletter-signup"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "newsletter_signup_function_name" {
  description = "Newsletter signup Lambda function name"
  value       = aws_lambda_function.newsletter_signup.function_name
}

output "newsletter_signup_function_arn" {
  description = "Newsletter signup Lambda function ARN"
  value       = aws_lambda_function.newsletter_signup.arn
}
