# ============================================================================
# REIT Sheet - Social Classifier Lambda
# ============================================================================
# Classifies press releases for social media pipeline
# Uses Claude Haiku to determine materiality, sensitivity, category
#
# Routing:
# - Scheduling calls → skipped_auto
# - All other releases → social-posting queue

# -----------------------------------------------------------------------------
# Social Classifier Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "social_classifier" {
  filename      = "${path.module}/../lambdas/social-classifier/social-classifier-with-deps.zip"
  function_name = "${var.project_name}-social-classifier"
  role          = aws_iam_role.social_classifier_role.arn
  handler       = "handler.handler"
  runtime       = var.lambda_runtime
  timeout       = 60 # 1 minute (Haiku is fast)
  memory_size   = 256
  description   = "Social classifier - determines materiality and category for social posting"

  source_code_hash = fileexists("${path.module}/../lambdas/social-classifier/social-classifier-with-deps.zip") ? filebase64sha256("${path.module}/../lambdas/social-classifier/social-classifier-with-deps.zip") : null

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REIT_NEWS_TABLE      = aws_dynamodb_table.reit_news_v2.name
      SOCIAL_STATE_TABLE   = aws_dynamodb_table.social_state.name
      SOCIAL_POSTING_QUEUE = aws_sqs_queue.social_posting.url
      LOG_LEVEL            = "INFO"
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Social-Classifier-Lambda"
    Description    = "Classifies-releases-for-social-media-posting"
    Function       = "social-classification"
    Trigger        = "sqs-social-classify-queue"
    Downstream     = "social-posting-queue"
    ProcessingTime = "approx-2-5s"
    Criticality    = "medium"
  })

  depends_on = [
    aws_cloudwatch_log_group.social_classifier_logs
  ]
}

# -----------------------------------------------------------------------------
# Social Classifier Lambda - IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "social_classifier_role" {
  name = "${var.project_name}-social-classifier-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
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
    }]
  })

  tags = merge(local.iam_tags, {
    Name = "Social-Classifier-Lambda-Role"
  })
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "social_classifier_basic" {
  role       = aws_iam_role.social_classifier_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# X-Ray tracing policy
resource "aws_iam_role_policy_attachment" "social_classifier_xray" {
  role       = aws_iam_role.social_classifier_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Custom policy for DynamoDB, SQS, Secrets Manager
resource "aws_iam_role_policy" "social_classifier_custom" {
  name = "${var.project_name}-social-classifier-policy"
  role = aws_iam_role.social_classifier_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:PutItem"
        ]
        Resource = [
          aws_dynamodb_table.reit_news_v2.arn,
          aws_dynamodb_table.social_state.arn
        ]
      },
      {
        Sid    = "SQSReceive"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.social_classify.arn
      },
      {
        Sid    = "SQSSend"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.social_posting.arn
      },
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.flask_secrets.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Social Classifier Lambda - SQS Trigger
# -----------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "social_classifier_trigger" {
  event_source_arn = aws_sqs_queue.social_classify.arn
  function_name    = aws_lambda_function.social_classifier.arn
  batch_size       = 1 # Process one at a time (each needs Haiku call)
  enabled          = false # Disabled until X/Meta accounts are set up

  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [
    aws_lambda_function.social_classifier,
    aws_sqs_queue.social_classify
  ]
}

# -----------------------------------------------------------------------------
# Social Classifier Lambda - CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "social_classifier_logs" {
  name              = "/aws/lambda/${var.project_name}-social-classifier"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name   = "Social-Classifier-Lambda-Logs"
    Lambda = "${var.project_name}-social-classifier"
  })
}

# -----------------------------------------------------------------------------
# Social Classifier Lambda - CloudWatch Alarm (Error Rate)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "social_classifier_errors" {
  alarm_name          = "${var.project_name}-social-classifier-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Social classifier Lambda error rate high"

  dimensions = {
    FunctionName = aws_lambda_function.social_classifier.function_name
  }

  tags = merge(local.monitoring_tags, {
    Name = "Social-Classifier-Error-Alarm"
  })
}
