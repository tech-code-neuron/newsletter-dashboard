# ============================================================================
# REIT Sheet - Social Media Pipeline Queues
# ============================================================================
# SQS queues for the social media posting pipeline
# - Classify queue: receives releases from enricher/body-fetcher
# - Posting queue: receives classified releases for X/IG workers

# -----------------------------------------------------------------------------
# Social Classify Queue - Dead Letter Queue
# -----------------------------------------------------------------------------

resource "aws_sqs_queue" "social_classify_dlq" {
  name                       = "${var.project_name}-social-classify-dlq"
  visibility_timeout_seconds = 1800
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Social-Classify-DLQ"
    Description = "Dead-letter-queue-for-failed-classification-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = "${var.project_name}-social-classify-queue"
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Social Classify Queue
# -----------------------------------------------------------------------------
# Receives releases from enricher and body-fetcher
# Classifier Lambda determines materiality, sensitivity, category

resource "aws_sqs_queue" "social_classify" {
  name                       = "${var.project_name}-social-classify-queue"
  visibility_timeout_seconds = 180 # 3 minutes (Haiku classification is fast)
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.social_classify_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Social-Classify-Queue"
    Description    = "Queue-for-releases-awaiting-social-media-classification"
    QueueType      = "standard"
    Consumer       = "lambda-social-classifier"
    Producer       = "lambda-enricher+lambda-body-fetcher"
    MessageType    = "classification-job"
    ProcessingTime = "approx-2-5s"
  })
}

# -----------------------------------------------------------------------------
# Social Posting Queue - Dead Letter Queue
# -----------------------------------------------------------------------------

resource "aws_sqs_queue" "social_posting_dlq" {
  name                       = "${var.project_name}-social-posting-dlq"
  visibility_timeout_seconds = 1800
  message_retention_seconds  = var.sqs_dlq_message_retention_seconds

  tags = merge(local.queue_tags, {
    Name        = "REIT-Sheet-Social-Posting-DLQ"
    Description = "Dead-letter-queue-for-failed-social-posting-operations"
    QueueType   = "dead-letter-queue"
    SourceQueue = "${var.project_name}-social-posting-queue"
    AlertOn     = "message-arrival"
  })
}

# -----------------------------------------------------------------------------
# Social Posting Queue
# -----------------------------------------------------------------------------
# Receives classified releases from classifier
# X worker and IG worker consume from this queue

resource "aws_sqs_queue" "social_posting" {
  name                       = "${var.project_name}-social-posting-queue"
  visibility_timeout_seconds = 120 # 2 minutes
  message_retention_seconds  = var.sqs_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.social_posting_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(local.queue_tags, {
    Name           = "REIT-Sheet-Social-Posting-Queue"
    Description    = "Queue-for-releases-ready-for-social-media-posting"
    QueueType      = "standard"
    Consumer       = "lambda-social-x-worker+lambda-social-ig-worker"
    Producer       = "lambda-social-classifier"
    MessageType    = "posting-job"
    ProcessingTime = "approx-5-10s"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "social_classify_queue_url" {
  value       = aws_sqs_queue.social_classify.url
  description = "Social classify queue URL"
}

output "social_classify_queue_arn" {
  value       = aws_sqs_queue.social_classify.arn
  description = "Social classify queue ARN"
}

output "social_posting_queue_url" {
  value       = aws_sqs_queue.social_posting.url
  description = "Social posting queue URL"
}

output "social_posting_queue_arn" {
  value       = aws_sqs_queue.social_posting.arn
  description = "Social posting queue ARN"
}
