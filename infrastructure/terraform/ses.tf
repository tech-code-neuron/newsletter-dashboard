# ============================================================================
# AWS SES (Simple Email Service) Configuration - Production Ready
# ============================================================================
# Manages domain verification, DKIM, receipt rules, and reputation monitoring
#
# Email Addresses:
#   - alerts@reitsheet.co (primary - receives IR press release emails)
#
# Architecture:
#   Incoming Email → SES Receipt Rule → S3 Bucket → Lambda Producer
#
# SOLID Principles:
#   - Single Responsibility: Each resource manages one SES concern
#   - Open/Closed: Easy to add notification subscriptions via data-driven config
#   - No Hardcoded Values: All thresholds and emails in variables.tf
#   - DRY: Notification types defined as data, not duplicated code
#
# Note: SES is only available in specific regions (us-east-1, us-west-2, eu-west-1)

# -----------------------------------------------------------------------------
# Domain Identity Verification
# -----------------------------------------------------------------------------

resource "aws_ses_domain_identity" "reitsheet" {
  domain = var.domain_name
}

# DKIM signing for email authentication (improves deliverability)
resource "aws_ses_domain_dkim" "reitsheet" {
  domain = aws_ses_domain_identity.reitsheet.domain
}

# NOTE: Domain verification is MANUAL
# After terraform apply, add DNS records from outputs:
#   - ses_domain_verification_token → TXT record
#   - ses_dkim_tokens → 3 CNAME records
# Then verify with: ses_verification_check_command (see outputs)
#
# We do NOT use aws_ses_domain_identity_verification because:
#   - It blocks terraform apply until verification completes
#   - DNS records must be added externally (Cloudflare/etc)
#   - Creates brittle deployments that fail on first run
#   - Violates Single Responsibility (verification != configuration)

# -----------------------------------------------------------------------------
# Bounce and Complaint Handling (Production Requirement)
# -----------------------------------------------------------------------------

# SOLID: Data-driven notification configuration
locals {
  ses_notification_types = {
    bounce = {
      name            = "Bounce"
      description     = "Hard bounces and delivery failures"
      alarm_threshold = var.ses_bounce_rate_threshold
    }
    complaint = {
      name            = "Complaint"
      description     = "Spam complaints and abuse reports"
      alarm_threshold = var.ses_complaint_rate_threshold
    }
  }
}

# SNS topics for bounce and complaint notifications
resource "aws_sns_topic" "ses_notifications" {
  for_each = local.ses_notification_types

  name         = "${var.project_name}-ses-${lower(each.key)}"
  display_name = "SES ${each.value.name} Notifications"

  tags = merge(local.common_tags, {
    Purpose          = "SES ${each.value.description}"
    NotificationType = each.value.name
  })
}

# Configure SES to publish notifications to SNS
resource "aws_ses_identity_notification_topic" "notifications" {
  for_each = local.ses_notification_types

  topic_arn                = aws_sns_topic.ses_notifications[each.key].arn
  notification_type        = each.value.name
  identity                 = aws_ses_domain_identity.reitsheet.domain
  include_original_headers = true # Include full headers for debugging
}

# Email subscription for operations team
resource "aws_sns_topic_subscription" "notification_email" {
  for_each = local.ses_notification_types

  topic_arn = aws_sns_topic.ses_notifications[each.key].arn
  protocol  = "email"
  endpoint  = var.ses_notification_email
}


# -----------------------------------------------------------------------------
# Receipt Rule Set and Rules
# -----------------------------------------------------------------------------

resource "aws_ses_receipt_rule_set" "reitsheet" {
  rule_set_name = "${var.project_name}-receipt-rules"
}

# Make this rule set active (only one can be active at a time)
resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.reitsheet.rule_set_name
}

# Receipt Rule: Route Emails to S3 and Forward to Personal Email
resource "aws_ses_receipt_rule" "route_to_s3" {
  name          = "route-emails-to-s3"
  rule_set_name = aws_ses_receipt_rule_set.reitsheet.rule_set_name
  enabled       = true
  scan_enabled  = true # Anti-spam and anti-virus scanning

  # SOLID: Open/Closed - add new recipients without modifying logic
  recipients = [
    "alerts@${var.domain_name}",
    # Add more email addresses here as needed:
    # "ir@${var.domain_name}",
    # "releases@${var.domain_name}",
  ]

  # Action 1: Store in S3 (for Lambda processing)
  s3_action {
    bucket_name       = aws_s3_bucket.email_ingest.id
    object_key_prefix = var.s3_email_prefix
    position          = 1

    # Optional: KMS encryption for emails at rest
    # kms_key_arn = aws_kms_key.email_encryption.arn
  }

  # Action 2: Forward to personal email (for manual review)
  lambda_action {
    function_arn    = aws_lambda_function.email_forwarder.arn
    invocation_type = "Event" # Async - don't wait for forwarding to complete
    position        = 2
  }

  depends_on = [
    aws_s3_bucket_policy.email_ingest,
    aws_ses_receipt_rule_set.reitsheet,
    aws_lambda_permission.allow_ses_forwarder
  ]
}

# Receipt Rule: Admin emails (DMARC reports, privacy requests)
resource "aws_ses_receipt_rule" "admin_emails" {
  name          = "admin-emails"
  rule_set_name = aws_ses_receipt_rule_set.reitsheet.rule_set_name
  after         = aws_ses_receipt_rule.route_to_s3.name
  enabled       = true
  scan_enabled  = true

  recipients = [
    "dmarc@${var.domain_name}",
    "privacy@${var.domain_name}",
  ]

  # Store in S3 under admin/ prefix
  s3_action {
    bucket_name       = aws_s3_bucket.email_ingest.id
    object_key_prefix = "admin/"
    position          = 1
  }

  # Notify ops team of new admin emails
  sns_action {
    topic_arn = aws_sns_topic.ses_notifications["bounce"].arn
    position  = 2
  }

  depends_on = [
    aws_s3_bucket_policy.email_ingest,
    aws_ses_receipt_rule_set.reitsheet,
    aws_ses_receipt_rule.route_to_s3
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Monitoring and Alarms (Production Requirement)
# -----------------------------------------------------------------------------

# Reputation Metrics Alarms (only if enabled)
resource "aws_cloudwatch_metric_alarm" "reputation_metrics" {
  for_each = var.ses_enable_reputation_monitoring ? local.ses_notification_types : {}

  alarm_name          = "${var.project_name}-ses-${lower(each.key)}-rate-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = each.value.name == "Bounce" ? "Reputation.BounceRate" : "Reputation.ComplaintRate"
  namespace           = "AWS/SES"
  period              = 3600 # 1 hour
  statistic           = "Average"
  threshold           = each.value.alarm_threshold
  alarm_description   = "SES ${each.value.name} rate exceeds ${each.value.alarm_threshold * 100}%"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.ses_notifications[each.key].arn]

  tags = merge(local.common_tags, {
    Severity   = "high"
    MetricType = "reputation"
  })
}

# Sending Quota Alarm (warns at threshold percentage)
resource "aws_cloudwatch_metric_alarm" "quota_warning" {
  alarm_name          = "${var.project_name}-ses-quota-warning"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Send"
  namespace           = "AWS/SES"
  period              = 86400 # 24 hours
  statistic           = "Sum"
  # Threshold calculated as: sandbox_limit * warning_threshold = 200 * 0.75 = 150
  # NOTE: This will need updating after exiting sandbox
  threshold          = 200 * var.ses_quota_warning_threshold
  alarm_description  = "SES approaching daily sending quota (${var.ses_quota_warning_threshold * 100}% threshold)"
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn] # Reuse bounce topic

  tags = merge(local.common_tags, {
    Severity   = "warning"
    MetricType = "quota"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ses_domain_verification_token" {
  description = "TXT record to add to DNS for domain verification"
  value       = aws_ses_domain_identity.reitsheet.verification_token
}

output "ses_dkim_tokens" {
  description = "CNAME records to add to DNS for DKIM signing"
  value       = aws_ses_domain_dkim.reitsheet.dkim_tokens
}

output "ses_rule_set_name" {
  description = "Active SES receipt rule set"
  value       = aws_ses_receipt_rule_set.reitsheet.rule_set_name
}

output "active_email_addresses" {
  description = "Email addresses configured to receive press releases"
  value       = aws_ses_receipt_rule.route_to_s3.recipients
}

output "ses_notification_topics" {
  description = "SNS topics for SES bounce and complaint notifications"
  value = {
    for k, v in aws_sns_topic.ses_notifications : k => {
      arn  = v.arn
      name = v.name
    }
  }
}

output "ses_verification_check_command" {
  description = "Command to verify domain is verified in SES"
  value       = "aws ses get-identity-verification-attributes --identities ${var.domain_name} --region ${var.aws_region}"
}

output "ses_dkim_check_command" {
  description = "Command to verify DKIM is enabled and verified"
  value       = "aws ses get-identity-dkim-attributes --identities ${var.domain_name} --region ${var.aws_region}"
}

output "ses_quota_check_command" {
  description = "Command to check current SES sending quota and usage"
  value       = "aws sesv2 get-account --region ${var.aws_region} | jq '.SendQuota'"
}

output "ses_sandbox_status_command" {
  description = "Command to check if account is in SES sandbox"
  value       = "aws sesv2 get-account --region ${var.aws_region} | jq '.ProductionAccessEnabled'"
}
