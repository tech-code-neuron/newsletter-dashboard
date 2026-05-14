# ============================================================================
# Email Forwarder Lambda
# ============================================================================
# Forwards emails from alerts@reitsheet.co to user's personal email
# Allows manual review of IR signup confirmations while still processing
# programmatically

# -----------------------------------------------------------------------------
# Forwarder Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "email_forwarder" {
  filename      = "${path.module}/../lambdas/email-forwarder/email-forwarder-latest.zip"
  function_name = "${var.project_name}-email-forwarder"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = 30
  memory_size   = 256
  description   = "Forwards emails from alerts@ to reitsheet@outlook.com for manual review"

  source_code_hash = filebase64sha256("${path.module}/../lambdas/email-forwarder/email-forwarder-latest.zip")

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      FORWARD_TO              = var.email_forward_destination
      FORWARD_FROM            = "alerts@${var.domain_name}"
      S3_BUCKET               = aws_s3_bucket.email_ingest.bucket
      SES_REGION              = var.aws_region
      FORWARD_LOG_TABLE       = aws_dynamodb_table.forward_log.name
      EMAIL_STATS_TABLE       = aws_dynamodb_table.email_stats.name
      FORWARD_FILTER_PATTERNS = var.email_forward_filter_patterns
    }
  }

  tags = merge(local.lambda_tags, {
    Name        = "REIT-Sheet-Email-Forwarder-Lambda"
    Description = "Forwards-emails-to-personal-inbox-for-manual-review"
    Function    = "email-forwarder"
    Trigger     = "ses-receipt-rule"
  })

  depends_on = [
    aws_cloudwatch_log_group.email_forwarder_logs
  ]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "email_forwarder_logs" {
  name              = "/aws/lambda/${var.project_name}-email-forwarder"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name = "REIT-Sheet-Email-Forwarder-Logs"
  })
}

# Lambda Permission for SES
resource "aws_lambda_permission" "allow_ses_forwarder" {
  statement_id   = "AllowExecutionFromSES"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.email_forwarder.function_name
  principal      = "ses.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}

# -----------------------------------------------------------------------------
# IAM - SES Send Permission for Forwarder
# -----------------------------------------------------------------------------
# Allow forwarder Lambda to send emails via SES

resource "aws_iam_role_policy" "lambda_ses_send" {
  name = "${var.project_name}-lambda-ses-send"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SESSendRawEmail"
        Effect = "Allow"
        Action = [
          "ses:SendRawEmail",
          "ses:SendEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "email_forwarder_function_name" {
  description = "Email forwarder Lambda function name"
  value       = aws_lambda_function.email_forwarder.function_name
}

output "email_forward_destination" {
  description = "Emails are forwarded to this address"
  value       = var.email_forward_destination
}
