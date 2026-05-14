# 8-K SEC Filing Ingestion Infrastructure
#
# Components:
# - DynamoDB table for 8-K disclosures
# - SQS FIFO queue for 8K processor
# - 8K-Fetcher Lambda (EventBridge triggered)
# - 8K-Processor Lambda (SQS triggered)

# =============================================================================
# DynamoDB Table: reitsheet-8k-disclosures
# =============================================================================

resource "aws_dynamodb_table" "sec_8k_disclosures" {
  name         = "reitsheet-8k-disclosures"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "filing_url"

  attribute {
    name = "filing_url"
    type = "S"
  }

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "filing_date"
    type = "S"
  }

  # GSI for querying by ticker and date
  global_secondary_index {
    name            = "ticker-date-index"
    hash_key        = "ticker"
    range_key       = "filing_date"
    projection_type = "ALL"
  }

  tags = {
    Name        = "reitsheet-8k-disclosures"
    Environment = "production"
    Project     = "reit-newsletter"
  }
}

# =============================================================================
# SQS FIFO Queue: reitsheet-8k-processor-queue
# =============================================================================

resource "aws_sqs_queue" "sec_8k_processor" {
  name                        = "reitsheet-8k-processor-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  deduplication_scope         = "messageGroup"
  fifo_throughput_limit       = "perMessageGroupId"

  visibility_timeout_seconds = 1080  # 18 minutes (Lambda timeout + 3 min safety margin)
  message_retention_seconds  = 1209600  # 14 days
  receive_wait_time_seconds  = 20  # Long polling

  tags = {
    Name        = "reitsheet-8k-processor-queue"
    Environment = "production"
    Project     = "reit-newsletter"
  }
}

resource "aws_sqs_queue" "sec_8k_processor_dlq" {
  name                      = "reitsheet-8k-processor-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600  # 14 days

  tags = {
    Name        = "reitsheet-8k-processor-dlq"
    Environment = "production"
    Project     = "reit-newsletter"
  }
}

resource "aws_sqs_queue_redrive_policy" "sec_8k_processor" {
  queue_url = aws_sqs_queue.sec_8k_processor.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.sec_8k_processor_dlq.arn
    maxReceiveCount     = 3
  })
}

# =============================================================================
# Lambda: 8K-Fetcher
# =============================================================================

resource "aws_lambda_function" "sec_8k_fetcher" {
  function_name = "reitsheet-8k-fetcher"
  role          = aws_iam_role.sec_8k_fetcher.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300  # 5 minutes
  memory_size   = 256

  filename         = "${path.module}/../lambdas/8k-fetcher/8k-fetcher-with-deps.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambdas/8k-fetcher/8k-fetcher-with-deps.zip")

  environment {
    variables = {
      COMPANIES_TABLE    = "reitsheet-companies-config"
      FILINGS_TABLE      = aws_dynamodb_table.sec_8k_disclosures.name
      PROCESSOR_QUEUE_URL = aws_sqs_queue.sec_8k_processor.url
    }
  }

  tags = {
    Name        = "reitsheet-8k-fetcher"
    Environment = "production"
    Project     = "reit-newsletter"
  }
}

# IAM Role for 8K-Fetcher
resource "aws_iam_role" "sec_8k_fetcher" {
  name = "reitsheet-8k-fetcher-role"

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
}

resource "aws_iam_role_policy" "sec_8k_fetcher" {
  name = "reitsheet-8k-fetcher-policy"
  role = aws_iam_role.sec_8k_fetcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:GetItem"
        ]
        Resource = [
          "arn:aws:dynamodb:us-east-1:*:table/reitsheet-companies-config",
          aws_dynamodb_table.sec_8k_disclosures.arn
        ]
      },
      {
        # Processor needs to write filings to DynamoDB
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.sec_8k_disclosures.arn
      },
      {
        # Fetcher sends messages to queue
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.sec_8k_processor.arn
      },
      {
        # Processor receives messages from queue (required for SQS trigger)
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.sec_8k_processor.arn
      },
      {
        # Processor uses Bedrock for AI extraction
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"
      }
    ]
  })
}

# EventBridge Schedule for 8K-Fetcher (3x daily on weekdays)
# NOTE: Times are in UTC. During EDT (Mar-Nov), subtract 4 hours. During EST (Nov-Mar), subtract 5 hours.
resource "aws_cloudwatch_event_rule" "sec_8k_fetcher_morning" {
  name                = "reitsheet-8k-fetcher-morning"
  description         = "Trigger 8K-Fetcher at 8:05 AM ET weekdays (12:05 UTC during EDT)"
  schedule_expression = "cron(5 12 ? * MON-FRI *)"  # 12:05 UTC = 8:05 AM EDT
}

resource "aws_cloudwatch_event_rule" "sec_8k_fetcher_midday" {
  name                = "reitsheet-8k-fetcher-midday"
  description         = "Trigger 8K-Fetcher at 9:00 AM EDT weekdays"
  schedule_expression = "cron(0 13 ? * MON-FRI *)"  # 13:00 UTC = 9:00 AM EDT
}

resource "aws_cloudwatch_event_rule" "sec_8k_fetcher_evening" {
  name                = "reitsheet-8k-fetcher-evening"
  description         = "Trigger 8K-Fetcher at 5:00 PM EDT weekdays"
  schedule_expression = "cron(0 21 ? * MON-FRI *)"  # 21:00 UTC = 5:00 PM EDT
}

resource "aws_cloudwatch_event_target" "sec_8k_fetcher_morning" {
  rule      = aws_cloudwatch_event_rule.sec_8k_fetcher_morning.name
  target_id = "8k-fetcher-morning"
  arn       = aws_lambda_function.sec_8k_fetcher.arn
}

resource "aws_cloudwatch_event_target" "sec_8k_fetcher_midday" {
  rule      = aws_cloudwatch_event_rule.sec_8k_fetcher_midday.name
  target_id = "8k-fetcher-midday"
  arn       = aws_lambda_function.sec_8k_fetcher.arn
}

resource "aws_cloudwatch_event_target" "sec_8k_fetcher_evening" {
  rule      = aws_cloudwatch_event_rule.sec_8k_fetcher_evening.name
  target_id = "8k-fetcher-evening"
  arn       = aws_lambda_function.sec_8k_fetcher.arn
}

resource "aws_lambda_permission" "sec_8k_fetcher_morning" {
  statement_id  = "AllowEventBridgeMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sec_8k_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sec_8k_fetcher_morning.arn
}

resource "aws_lambda_permission" "sec_8k_fetcher_midday" {
  statement_id  = "AllowEventBridgeMidday"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sec_8k_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sec_8k_fetcher_midday.arn
}

resource "aws_lambda_permission" "sec_8k_fetcher_evening" {
  statement_id  = "AllowEventBridgeEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sec_8k_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sec_8k_fetcher_evening.arn
}

# =============================================================================
# Lambda: 8K-Processor
# =============================================================================

resource "aws_lambda_function" "sec_8k_processor" {
  function_name = "reitsheet-8k-processor"
  role          = aws_iam_role.sec_8k_fetcher.arn  # Reuse same role
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 900  # 15 minutes for AI processing
  memory_size   = 512

  filename         = "${path.module}/../lambdas/8k-processor/8k-processor-with-deps.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambdas/8k-processor/8k-processor-with-deps.zip")

  environment {
    variables = {
      PRESS_RELEASES_TABLE = "reitsheet-reit-news-v2"
      DISCLOSURES_TABLE    = aws_dynamodb_table.sec_8k_disclosures.name
    }
  }

  tags = {
    Name        = "reitsheet-8k-processor"
    Environment = "production"
    Project     = "reit-newsletter"
  }
}

# SQS Trigger for 8K-Processor
resource "aws_lambda_event_source_mapping" "sec_8k_processor" {
  event_source_arn = aws_sqs_queue.sec_8k_processor.arn
  function_name    = aws_lambda_function.sec_8k_processor.arn
  batch_size       = 1
  enabled          = true
}

# =============================================================================
# Outputs
# =============================================================================

output "sec_8k_disclosures_table_name" {
  value = aws_dynamodb_table.sec_8k_disclosures.name
}

output "sec_8k_processor_queue_url" {
  value = aws_sqs_queue.sec_8k_processor.url
}

output "sec_8k_fetcher_function_name" {
  value = aws_lambda_function.sec_8k_fetcher.function_name
}
