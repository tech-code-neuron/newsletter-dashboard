# ============================================================================
# REIT Sheet - Enrichment Queue
# ============================================================================
# URL enrichment queue for Parser → Enricher flow
# Separates fast parsing from slow URL validation
# Enables independent scaling of Parser and Enricher

# -----------------------------------------------------------------------------
# Enrichment Queue - Dead Letter Queue
# -----------------------------------------------------------------------------
# Receives enrichment jobs that failed after max retries
# Common failures: company not found, all URLs invalid
# Retains for 14 days for troubleshooting

resource "aws_sqs_queue" "enrich_dlq" {
  name                       = "${var.project_name}-enrich-dlq"
  visibility_timeout_seconds = 1800 # 30 min (6x DLQ Processor timeout)
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Enrich-DLQ"
    Description = "Dead-letter-queue-for-failed-URL-enrichment-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = "${var.project_name}-enrich-queue"
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Enrichment Queue
# -----------------------------------------------------------------------------
# Receives enrichment jobs from Parser Lambda
# Enricher Lambda processes URL construction + validation
# Slower operations separated from fast parsing

resource "aws_sqs_queue" "enrich" {
  name                       = "${var.project_name}-enrich-queue"
  visibility_timeout_seconds = var.sqs_visibility_timeout # 3 minutes (URL validation takes time)
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.enrich_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Enrich-Queue"
    Description    = "Queue-for-URL-enrichment-jobs---constructs-and-validates-press-release-URLs"
    QueueType      = "standard"
    Consumer       = "lambda-enricher"
    Producer       = "lambda-parser"
    MessageType    = "enrichment-job"
    ProcessingTime = "approx-5-15s"
  })
}
