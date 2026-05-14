# ============================================================================
# REIT Sheet - Simple Scraper SQS Queue
# ============================================================================
# Handles 90% of companies using lightweight HTTP methods
# Significantly cheaper than Playwright scraper

# -----------------------------------------------------------------------------
# Simple Scraper Queue - Dead Letter Queue
# -----------------------------------------------------------------------------

resource "aws_sqs_queue" "simple_scraper_dlq" {
  name                       = "${var.project_name}-simple-scraper-dlq"
  visibility_timeout_seconds = 1800 # 30 min (6x DLQ Processor timeout)
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Simple-Scraper-DLQ"
    Description = "Dead-letter-queue-for-failed-simple-HTTP-scraping-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = "${var.project_name}-simple-scraper-queue"
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Simple Scraper Queue
# -----------------------------------------------------------------------------
# Receives jobs for simple HTTP scraping (curl_cffi, cloudscraper)
# Handles 90% of companies (all except JS-rendered sites)

resource "aws_sqs_queue" "simple_scraper" {
  name                       = "${var.project_name}-simple-scraper-queue"
  visibility_timeout_seconds = 120 # 2 minutes (simple scraping is fast)
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.simple_scraper_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Simple-Scraper-Queue"
    Description    = "Queue-for-simple-HTTP-scraping-jobs"
    QueueType      = "standard"
    Consumer       = "lambda-simple-scraper"
    Producer       = "lambda-scraper-router"
    MessageType    = "simple-scraping-job"
    ProcessingTime = "approx-5-10s"
    Companies      = "90-percent-of-all-companies"
    CostProfile    = "low"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarm - Simple Scraper DLQ
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "simple_scraper_dlq" {
  alarm_name          = "${var.project_name}-simple-scraper-dlq-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.dlq_alarm_evaluation_periods
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = var.dlq_alarm_period_seconds
  statistic           = "Average"
  threshold           = var.dlq_alarm_threshold
  alarm_description   = "Triggers when simple scraper DLQ receives failed messages"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.simple_scraper_dlq.name
  }

  tags = merge(local.monitoring_tags, {
    Name      = "simple-scraper-dlq-alarm"
    Severity  = "medium"
    AlertType = "operational"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "simple_scraper_queue_url" {
  description = "Simple scraper queue URL"
  value       = aws_sqs_queue.simple_scraper.url
}

output "simple_scraper_queue_arn" {
  description = "Simple scraper queue ARN"
  value       = aws_sqs_queue.simple_scraper.arn
}

output "simple_scraper_dlq_url" {
  description = "Simple scraper DLQ URL"
  value       = aws_sqs_queue.simple_scraper_dlq.url
}
