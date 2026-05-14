# ============================================================================
# REIT Sheet - Lambda Functions
# ============================================================================
# Serverless functions for email processing pipeline
# - Producer: S3 → SQS (triggered by S3 events)
# - Parser: Email parsing and link extraction (triggered by SQS)
# - Scraper: Newswire redirect resolution (triggered by SQS)

# -----------------------------------------------------------------------------
# Producer Lambda Function
# -----------------------------------------------------------------------------
# Triggered by S3 ObjectCreated events
# Generates idempotency key and sends metadata to parse queue
# First step in the processing pipeline

resource "aws_lambda_function" "producer" {
  filename      = "../lambdas/producer.zip"
  function_name = local.producer_function
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_short
  memory_size   = var.lambda_memory_size
  description   = "S3-to-SQS producer - generates idempotency keys for incoming emails and queues them for parsing"

  source_code_hash = filebase64sha256("../lambdas/producer.zip")

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      PARSE_QUEUE_URL                    = aws_sqs_queue.email_parse.url
      RATE_LIMIT_TABLE                   = aws_dynamodb_table.rate_limits.name
      WHITELIST_TABLE                    = aws_dynamodb_table.domain_whitelist.name
      S3_BUCKET_NAME                     = aws_s3_bucket.email_ingest.bucket
      EMAIL_MAX_SIZE_BYTES               = var.email_max_size_mb * 1024 * 1024
      EMAIL_RATE_LIMIT_PER_MINUTE        = var.email_rate_limit_per_minute
      EMAIL_RATE_LIMIT_PER_HOUR          = var.email_rate_limit_per_hour
      EMAIL_SPAM_FILTERING_ENABLED       = var.email_spam_filtering_enabled
      EMAIL_ATTACHMENT_FILTERING_ENABLED = var.email_attachment_filtering_enabled
      EMAIL_ALLOWED_ATTACHMENT_TYPES     = jsonencode(var.email_allowed_attachment_types)
      LOG_LEVEL                          = "INFO"
      PROJECT_NAME                       = var.project_name
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Producer-Lambda"
    Description    = "Processes-S3-events-and-queues-emails-for-parsing"
    Function       = "event-producer"
    Trigger        = "s3-object-created"
    Downstream     = "parse-queue"
    ProcessingTime = "approx-1-5s"
    Criticality    = "high"
  })

  depends_on = [
    aws_cloudwatch_log_group.producer_logs
  ]
}

# -----------------------------------------------------------------------------
# Producer Lambda - S3 Trigger Permission
# -----------------------------------------------------------------------------
# Grants S3 permission to invoke the producer Lambda

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.producer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.email_ingest.arn
}

# -----------------------------------------------------------------------------
# Parser Lambda Function
# -----------------------------------------------------------------------------
# Triggered by SQS parse queue messages
# Parses email body, extracts URLs, classifies as direct or newswire
# Routes newswire URLs to scrape queue, saves direct URLs to DynamoDB

resource "aws_lambda_function" "parser" {
  filename      = "../lambdas/parser.zip"
  function_name = local.parser_function
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_medium
  memory_size   = var.lambda_memory_size
  description   = "Email parser - extracts press release links, detects newswire redirects, routes to scraper or DynamoDB"

  source_code_hash = fileexists("../lambdas/parser.zip") ? filebase64sha256("../lambdas/parser.zip") : null

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.email_ingest.bucket
      SCRAPE_QUEUE_URL         = aws_sqs_queue.scrape.url
      ENRICH_QUEUE_URL         = aws_sqs_queue.enrich.url
      PLAYWRIGHT_QUEUE_URL     = aws_sqs_queue.playwright_scraper.url
      INBOUND_LOG_TABLE        = aws_dynamodb_table.inbound_log.name
      REIT_NEWS_TABLE          = aws_dynamodb_table.reit_news_v2.name
      COMPANIES_TABLE          = aws_dynamodb_table.companies_config.name
      USE_GSI_MATCHING         = "true"
      LOG_LEVEL                = "INFO"
      PROJECT_NAME             = var.project_name
      MAX_MESSAGE_AGE_MINUTES  = "30"  # Stale message prevention (Phase 1)
      CONFIG_CACHE_TTL_SECONDS = "300" # Company config cache TTL (5 minutes)
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Parser-Lambda"
    Description    = "Parses-emails-and-extracts-press-release-links"
    Function       = "email-parser"
    Trigger        = "sqs-parse-queue"
    Downstream     = "scrape-queue and dynamodb"
    ProcessingTime = "approx-30-60s"
    Criticality    = "high"
  })

  depends_on = [
    aws_cloudwatch_log_group.parser_logs
  ]
}

# -----------------------------------------------------------------------------
# Parser Lambda - SQS Trigger
# -----------------------------------------------------------------------------
# Event source mapping connects parse queue to parser Lambda

resource "aws_lambda_event_source_mapping" "parser_trigger" {
  event_source_arn = aws_sqs_queue.email_parse.arn
  function_name    = aws_lambda_function.parser.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]
}

# -----------------------------------------------------------------------------
# Scraper Lambda Function
# -----------------------------------------------------------------------------
# Triggered by SQS scrape queue messages
# Follows newswire redirects to extract company press release URLs
# Handles GlobeNewswire, Business Wire, PR Newswire

resource "aws_lambda_function" "scraper" {
  filename      = "../lambdas/scraper.zip"
  function_name = local.scraper_function
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_long
  memory_size   = var.lambda_memory_size
  description   = "Web scraper - resolves newswire redirects to company URLs and saves to DynamoDB"

  source_code_hash = filebase64sha256("../lambdas/scraper.zip")

  # X-Ray distributed tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REIT_NEWS_TABLE         = aws_dynamodb_table.reit_news_v2.name
      URL_CACHE_TABLE         = aws_dynamodb_table.url_cache.name
      LOG_LEVEL               = "INFO"
      PROJECT_NAME            = var.project_name
      USER_AGENT              = "REITSheet/1.0 (+https://reitsheet.co)"
      MAX_MESSAGE_AGE_MINUTES = "30" # Stale message prevention (Phase 1)
    }
  }

  tags = merge(local.lambda_tags, {
    Name           = "REIT-Sheet-Scraper-Lambda"
    Description    = "Resolves-newswire-redirects-to-company-press-release-URLs"
    Function       = "web-scraper"
    Trigger        = "sqs-scrape-queue"
    Downstream     = "dynamodb"
    ProcessingTime = "approx-10-30s"
    Criticality    = "medium"
  })

  depends_on = [
    aws_cloudwatch_log_group.scraper_logs
  ]
}

# -----------------------------------------------------------------------------
# Scraper Lambda - SQS Trigger
# -----------------------------------------------------------------------------
# Event source mapping connects scrape queue to scraper Lambda

resource "aws_lambda_event_source_mapping" "scraper_trigger" {
  event_source_arn = aws_sqs_queue.scrape.arn
  function_name    = aws_lambda_function.scraper.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # Retry configuration
  function_response_types = ["ReportBatchItemFailures"]
}
