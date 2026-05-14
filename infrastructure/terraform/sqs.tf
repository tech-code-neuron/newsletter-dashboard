# ============================================================================
# REIT Sheet - SQS Queue Configuration
# ============================================================================
# Message queues for asynchronous Lambda processing
# - Parse Queue: Email parsing and link extraction
# - Scrape Queue: Newswire URL resolution
# - Dead Letter Queues: Failed message handling

# -----------------------------------------------------------------------------
# Email Parse Queue - Dead Letter Queue
# -----------------------------------------------------------------------------
# Receives messages that failed processing after max_receive_count attempts
# Retains for 14 days to allow manual inspection and debugging
# Triggers CloudWatch alarm for operational visibility

resource "aws_sqs_queue" "email_parse_dlq" {
  name                       = local.parse_dlq_name
  visibility_timeout_seconds = 1800 # 30 min (6x DLQ Processor timeout)
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Email-Parse-DLQ"
    Description = "Dead-letter-queue-for-failed-email-parsing-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = local.parse_queue_name
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Email Parse Queue
# -----------------------------------------------------------------------------
# Receives S3 metadata from Producer Lambda
# Parser Lambda reads from this queue to extract press release links
# Messages expire after 1 day if not processed

resource "aws_sqs_queue" "email_parse" {
  name                       = local.parse_queue_name
  visibility_timeout_seconds = var.sqs_visibility_timeout
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.email_parse_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Email-Parse-Queue"
    Description    = "Queue-for-email-parsing-jobs---extracts-press-release-links-from-email-body"
    QueueType      = "standard"
    Consumer       = "lambda-parser"
    Producer       = "lambda-producer"
    MessageType    = "s3-email-metadata"
    ProcessingTime = "approx-30-60s"
  })
}

# -----------------------------------------------------------------------------
# Scrape Queue - Dead Letter Queue
# -----------------------------------------------------------------------------
# Receives scraping jobs that failed after max retries
# Common failures: timeouts, rate limits, 404s
# Retains for 14 days for troubleshooting

resource "aws_sqs_queue" "scrape_dlq" {
  name                       = local.scrape_dlq_name
  visibility_timeout_seconds = 1800 # 30 min (6x DLQ Processor timeout)
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Scrape-DLQ"
    Description = "Dead-letter-queue-for-failed-web-scraping-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = local.scrape_queue_name
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Scrape Queue
# -----------------------------------------------------------------------------
# Receives newswire redirect URLs that need resolution
# Scraper Lambda follows redirects to find company press release URLs
# Handles GlobeNewswire, Business Wire, PR Newswire

resource "aws_sqs_queue" "scrape" {
  name                       = local.scrape_queue_name
  visibility_timeout_seconds = var.sqs_visibility_timeout
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scrape_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Scrape-Queue"
    Description    = "Queue-for-web-scraping-jobs---resolves-newswire-redirects-to-company-URLs"
    QueueType      = "standard"
    Consumer       = "lambda-scraper"
    Producer       = "lambda-parser"
    MessageType    = "newswire-redirect-url"
    ProcessingTime = "approx-10-30s"
  })
}

# -----------------------------------------------------------------------------
# Playwright Scraper Queue - Dead Letter Queue
# -----------------------------------------------------------------------------
# Handles failed JavaScript-rendered scraping jobs
# Typically failures: timeouts, page load errors, DOM changes
# Retains for 14 days for debugging and manual retry

resource "aws_sqs_queue" "playwright_scraper_dlq" {
  name                       = local.playwright_dlq_name
  visibility_timeout_seconds = 1800 # 30 min (6x DLQ Processor timeout)
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Playwright-Scraper-DLQ"
    Description = "Dead-letter-queue-for-failed-JavaScript-scraping-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = local.playwright_queue_name
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Playwright Scraper Queue
# -----------------------------------------------------------------------------
# Receives jobs for JavaScript-rendered press release pages
# Processed by Playwright Lambda using headless Chrome
# Companies requiring JS: EPRT (Essential Properties)
# Longer timeout due to browser startup and page rendering

resource "aws_sqs_queue" "playwright_scraper" {
  name                       = local.playwright_queue_name
  visibility_timeout_seconds = var.sqs_playwright_visibility_timeout
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.playwright_scraper_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Playwright-Scraper-Queue"
    Description    = "Queue-for-JavaScript-rendered-press-releases"
    QueueType      = "standard"
    Consumer       = "lambda-playwright-scraper"
    Producer       = "lambda-parser"
    MessageType    = "javascript-scraping-job"
    ProcessingTime = "approx-30-90s"
    Companies      = "EPRT"
  })
}
