# ============================================================================
# REIT Sheet - ECS IAM Configuration
# ============================================================================
# IAM roles for ECS task execution and application permissions
#
# Two roles:
#   - Execution Role: Used by ECS to pull images, send logs, get secrets
#   - Task Role: Used by the application to access AWS services

# -----------------------------------------------------------------------------
# ECS Task Execution Role
# -----------------------------------------------------------------------------
# This role is used by the ECS agent to:
#   - Pull container images from ECR
#   - Send logs to CloudWatch
#   - Retrieve secrets from Secrets Manager

resource "aws_iam_role" "ecs_execution" {
  name        = "${var.project_name}-ecs-execution-role"
  description = "ECS task execution role for Flask application"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name     = "${var.project_name}-ecs-execution-role"
    RoleType = "execution-role"
  })
}

# Attach AWS managed policy for basic ECS execution
resource "aws_iam_role_policy_attachment" "ecs_execution_basic" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for Secrets Manager access
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.project_name}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.flask_secrets.arn,
          aws_secretsmanager_secret.cognito_config.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# ECS Task Role
# -----------------------------------------------------------------------------
# This role is used by the application itself to access AWS services:
#   - DynamoDB for data storage
#   - S3 for reading emails
#   - SES for sending emails (future)

resource "aws_iam_role" "ecs_task" {
  name        = "${var.project_name}-ecs-task-role"
  description = "ECS task role for Flask application AWS access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.iam_tags, {
    Name     = "${var.project_name}-ecs-task-role"
    RoleType = "task-role"
  })
}

# Task role policy - application permissions
resource "aws_iam_role_policy" "ecs_task" {
  name = "${var.project_name}-ecs-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB - Full access to REIT tables
      {
        Sid    = "DynamoDBTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable",
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn,
          "${aws_dynamodb_table.reit_news_v2.arn}/index/*",
          aws_dynamodb_table.companies_config.arn,
          "${aws_dynamodb_table.companies_config.arn}/index/*",
          aws_dynamodb_table.url_test_comments.arn,
          "${aws_dynamodb_table.url_test_comments.arn}/index/*",
          aws_dynamodb_table.press_release_audit.arn,
          "${aws_dynamodb_table.press_release_audit.arn}/index/*",
          aws_dynamodb_table.newsletters.arn,
          "${aws_dynamodb_table.newsletters.arn}/index/*",
          aws_dynamodb_table.review_emails.arn,
          "${aws_dynamodb_table.review_emails.arn}/index/*",
          aws_dynamodb_table.relevance_decisions.arn,
          "${aws_dynamodb_table.relevance_decisions.arn}/index/*"
        ]
      },

      # S3 - Read emails for review
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

      # CloudWatch - Write application metrics
      {
        Sid    = "CloudWatchMetricsAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "${var.project_name}/flask-app"
          }
        }
      },

      # Secrets Manager - Read Cognito config
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.cognito_config.arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ecs_execution_role_arn" {
  description = "ECS execution role ARN"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN"
  value       = aws_iam_role.ecs_task.arn
}
