# ============================================================================
# Press Release Pipeline - Terraform Variables
# ============================================================================
# All configurable parameters for the infrastructure
# Update these values to customize deployment

# -----------------------------------------------------------------------------
# Core Configuration
# -----------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for all resources (SES only available in us-east-1, us-west-2, eu-west-1)"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Domain name for receiving emails (must be verified in SES)"
  type        = string
  default     = "reitsheet.co"
}

variable "project_name" {
  description = "Project name used as prefix for all resource names"
  type        = string
  default     = "reitsheet"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

# -----------------------------------------------------------------------------
# Lambda Configuration
# -----------------------------------------------------------------------------

variable "lambda_timeout_short" {
  description = "Timeout in seconds for simple Lambda functions (S3 → SQS)"
  type        = number
  default     = 60
}

variable "lambda_timeout_medium" {
  description = "Timeout in seconds for email parsing Lambda"
  type        = number
  default     = 180
}

variable "lambda_timeout_long" {
  description = "Timeout in seconds for web scraping Lambda"
  type        = number
  default     = 300
}

variable "lambda_runtime" {
  description = "Python runtime version for Lambda functions"
  type        = string
  default     = "python3.11"
}

variable "lambda_memory_size" {
  description = "Memory allocation in MB for Lambda functions"
  type        = number
  default     = 256
}

# -----------------------------------------------------------------------------
# S3 Configuration
# -----------------------------------------------------------------------------

variable "s3_lifecycle_days" {
  description = "Number of days to retain emails in S3 before automatic deletion"
  type        = number
  default     = 30
}

variable "s3_email_prefix" {
  description = "S3 key prefix for incoming emails"
  type        = string
  default     = "incoming/"
}

# -----------------------------------------------------------------------------
# SQS Configuration
# -----------------------------------------------------------------------------

variable "sqs_visibility_timeout" {
  description = "SQS visibility timeout in seconds (should be 6x Lambda timeout)"
  type        = number
  default     = 1080 # 6x parser timeout (180s × 6) - AWS best practice
}

variable "sqs_message_retention_seconds" {
  description = "How long SQS retains messages before deletion (1 day)"
  type        = number
  default     = 86400
}

variable "sqs_dlq_message_retention_seconds" {
  description = "How long DLQ retains failed messages (14 days)"
  type        = number
  default     = 1209600
}

variable "sqs_max_receive_count" {
  description = "Maximum times a message can be received before moving to DLQ"
  type        = number
  default     = 5
}

variable "sqs_batch_size" {
  description = "Number of messages Lambda receives per batch from SQS"
  type        = number
  default     = 10 # Rate limiting: process 10 emails per batch (AWS requires batching_window for >10)
}

variable "sqs_playwright_visibility_timeout" {
  description = "SQS visibility timeout for Playwright queue (5 minutes for browser startup + rendering)"
  type        = number
  default     = 1800 # 6x playwright timeout (300s × 6) - AWS best practice
}

# -----------------------------------------------------------------------------
# DynamoDB Configuration
# -----------------------------------------------------------------------------

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "idempotency_ttl_days" {
  description = "Number of days to keep idempotency records (prevents reprocessing)"
  type        = number
  default     = 30
}

variable "dynamodb_point_in_time_recovery" {
  description = "Enable point-in-time recovery for DynamoDB tables"
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# CloudWatch Configuration
# -----------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Number of days to retain Lambda logs in CloudWatch (SECURITY: 30 days for incident investigation)"
  type        = number
  default     = 30 # Increased from 7 for forensic analysis capability
}

variable "dlq_alarm_threshold" {
  description = "Trigger alarm when DLQ message count exceeds this value"
  type        = number
  default     = 0
}

variable "dlq_alarm_evaluation_periods" {
  description = "Number of periods DLQ must exceed threshold before alarming"
  type        = number
  default     = 1
}

variable "dlq_alarm_period_seconds" {
  description = "Period in seconds for DLQ alarm evaluation (5 minutes)"
  type        = number
  default     = 300
}

# -----------------------------------------------------------------------------
# SES Configuration
# -----------------------------------------------------------------------------

variable "ses_quota_warning_threshold" {
  description = "Percentage of daily sending quota at which to trigger warning alarm (0.0-1.0)"
  type        = number
  default     = 0.75 # Alert at 75% of quota
}

variable "ses_bounce_rate_threshold" {
  description = "Maximum acceptable bounce rate before alarming (0.0-1.0)"
  type        = number
  default     = 0.05 # 5% bounce rate
}

variable "ses_complaint_rate_threshold" {
  description = "Maximum acceptable complaint rate before alarming (0.0-1.0)"
  type        = number
  default     = 0.001 # 0.1% complaint rate
}

variable "ses_notification_email" {
  description = "Email address to receive SES bounce/complaint notifications"
  type        = string
  default     = "ops@reitsheet.co"
}

variable "ses_enable_reputation_monitoring" {
  description = "Enable CloudWatch alarms for SES reputation metrics"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# Email Protection Configuration
# -----------------------------------------------------------------------------

variable "email_max_size_mb" {
  description = "Maximum email size in megabytes (emails larger than this are rejected)"
  type        = number
  default     = 5
}

variable "email_rate_limit_per_minute" {
  description = "Maximum emails per minute per sender domain"
  type        = number
  default     = 10
}

variable "email_rate_limit_per_hour" {
  description = "Maximum emails per hour per sender domain"
  type        = number
  default     = 100
}

variable "email_spam_filtering_enabled" {
  description = "Enable spam and virus filtering based on SES scan results"
  type        = bool
  default     = true
}

variable "email_attachment_filtering_enabled" {
  description = "Enable attachment type filtering (allow only images and PDFs)"
  type        = bool
  default     = true
}

variable "email_allowed_attachment_types" {
  description = "List of allowed MIME types for attachments"
  type        = list(string)
  default = [
    # Images
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    # Documents
    "application/pdf",
    # Email content
    "text/plain",
    "text/html",
    "multipart/mixed",
    "multipart/alternative",
    "multipart/related"
  ]
}

variable "email_forward_destination" {
  description = "Personal email address to forward alerts@ emails to for manual review"
  type        = string
  default     = "reitsheet@outlook.com"
}

variable "email_forward_filter_patterns" {
  description = "Comma-separated filter patterns for forwarding SEC emails (e.g., '8-K,8K,Form 8-K'). Only SEC emails are filtered - company IR/PR emails are always forwarded. Set to empty string to forward ALL emails."
  type        = string
  default     = "8-K,8K,Form 8-K,Form 8K"
}

variable "daily_summary_schedule" {
  description = "Cron expression for daily email summary (default: 6 PM EST = 11 PM UTC)"
  type        = string
  default     = "cron(0 23 * * ? *)" # 11 PM UTC = 6 PM EST
}

# -----------------------------------------------------------------------------
# URL Testing Dashboard Configuration
# -----------------------------------------------------------------------------

variable "url_testing_password" {
  description = "Password for URL testing dashboard API - MUST be provided via terraform.tfvars"
  type        = string
  # No default - must be provided via terraform.tfvars (gitignored)
  # Generate with: openssl rand -base64 24
  sensitive = true
}
