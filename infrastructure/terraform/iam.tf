# ============================================================================
# REIT Sheet - IAM Configuration
# ============================================================================
# Identity and access management for Lambda functions
# - Lambda execution role
# - Least privilege policies
# - Service-specific permissions

# -----------------------------------------------------------------------------
# Lambda Execution Role
# -----------------------------------------------------------------------------
# Allows Lambda service to assume this role and execute functions
# Follows AWS best practices for Lambda execution roles

resource "aws_iam_role" "lambda_role" {
  name        = local.lambda_role_name
  description = "Execution role for REIT Sheet Lambda functions with least-privilege permissions"

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
    Name        = "REIT-Sheet-Lambda-Role"
    Description = "IAM-role-for-Lambda-functions---producer-and-parser-and-scraper"
    RoleType    = "service-role"
    AssignedTo  = "lambda-functions"
    Principle   = "least-privilege"
  })
}

# -----------------------------------------------------------------------------
# Lambda Execution Policy
# -----------------------------------------------------------------------------
# Grants specific permissions needed by Lambda functions:
# - CloudWatch Logs: Write function logs
# - S3: Read incoming emails
# - SQS: Send/receive/delete messages
# - DynamoDB: Read/write press release data

resource "aws_iam_role_policy" "lambda_policy" {
  name = local.lambda_policy_name
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs - Required for all Lambda functions
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-*:*"
      },

      # S3 - Read emails for processing
      {
        Sid    = "S3EmailReadAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.email_ingest.arn,
          "${aws_s3_bucket.email_ingest.arn}/*"
        ]
      },

      # SQS - Message queue operations
      {
        Sid    = "SQSQueueAccess"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          aws_sqs_queue.email_parse.arn,
          aws_sqs_queue.scrape.arn,
          aws_sqs_queue.enrich.arn,
          aws_sqs_queue.simple_scraper.arn,
          aws_sqs_queue.playwright_scraper.arn,
          aws_sqs_queue.social_classify.arn,
          aws_sqs_queue.email_parse_dlq.arn,
          aws_sqs_queue.scrape_dlq.arn,
          aws_sqs_queue.enrich_dlq.arn,
          aws_sqs_queue.simple_scraper_dlq.arn,
          aws_sqs_queue.playwright_scraper_dlq.arn
        ]
      },

      # DynamoDB - Data persistence and idempotency
      {
        Sid    = "DynamoDBTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.inbound_log.arn,
          aws_dynamodb_table.reit_news_v2.arn,
          "${aws_dynamodb_table.reit_news_v2.arn}/index/*",
          aws_dynamodb_table.companies.arn,
          "${aws_dynamodb_table.companies.arn}/index/*",
          aws_dynamodb_table.companies_config.arn,
          "${aws_dynamodb_table.companies_config.arn}/index/*",
          aws_dynamodb_table.url_cache.arn,
          "${aws_dynamodb_table.url_cache.arn}/index/*",
          aws_dynamodb_table.rate_limits.arn,
          aws_dynamodb_table.domain_whitelist.arn,
          aws_dynamodb_table.email_tracking.arn,
          "${aws_dynamodb_table.email_tracking.arn}/index/*"
        ]
      }
    ]
  })
}
