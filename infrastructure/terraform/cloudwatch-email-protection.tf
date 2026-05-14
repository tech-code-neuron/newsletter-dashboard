# ============================================================================
# Email Protection CloudWatch Alarms
# ============================================================================
# Monitors rejected emails for operational awareness
# - Large file rejections (>5MB attempts)
# - Rate limit violations (spam/abuse detection)
# - Spam/virus detections
#
# SOLID: Single Responsibility - Each alarm monitors one protection metric

# -----------------------------------------------------------------------------
# Large File Rejection Alarm
# -----------------------------------------------------------------------------
# Triggers when emails over 5MB are being rejected
# Indicates potential need to increase limit or investigate sender

resource "aws_cloudwatch_metric_alarm" "large_file_rejections" {
  alarm_name          = "${var.project_name}-large-file-rejections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EmailRejected"
  namespace           = "${var.project_name}/EmailProtection"
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 5 # Alert if more than 5 large files rejected in 1 hour
  alarm_description   = "Emails over ${var.email_max_size_mb}MB are being rejected - may indicate legitimate large attachments"
  treat_missing_data  = "notBreaching"

  dimensions = {
    RejectionType = "size_limit_exceeded"
  }

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn]

  tags = merge(local.monitoring_tags, {
    Severity   = "warning"
    MetricType = "email-protection"
    AlertType  = "operational-awareness"
  })
}

# -----------------------------------------------------------------------------
# Rate Limit Violation Alarm
# -----------------------------------------------------------------------------
# Triggers when domains exceed rate limits
# Indicates potential spam/abuse or misconfigured sender

resource "aws_cloudwatch_metric_alarm" "rate_limit_violations" {
  alarm_name          = "${var.project_name}-rate-limit-violations"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EmailRejected"
  namespace           = "${var.project_name}/EmailProtection"
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 10 # Alert if more than 10 emails rate-limited in 1 hour
  alarm_description   = "Email rate limits exceeded (${var.email_rate_limit_per_minute}/min, ${var.email_rate_limit_per_hour}/hour) - possible spam or abuse"
  treat_missing_data  = "notBreaching"

  dimensions = {
    RejectionType = "minute_limit_exceeded"
  }

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn]

  tags = merge(local.monitoring_tags, {
    Severity   = "high"
    MetricType = "email-protection"
    AlertType  = "abuse-detection"
  })
}

# -----------------------------------------------------------------------------
# Spam Detection Alarm
# -----------------------------------------------------------------------------
# Triggers when spam emails are detected
# Indicates email address may be exposed or targeted

resource "aws_cloudwatch_metric_alarm" "spam_detected" {
  alarm_name          = "${var.project_name}-spam-detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EmailRejected"
  namespace           = "${var.project_name}/EmailProtection"
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 20 # Alert if more than 20 spam emails in 1 hour
  alarm_description   = "Spam emails detected - email address may be compromised or publicly exposed"
  treat_missing_data  = "notBreaching"

  dimensions = {
    RejectionType = "spam_detected"
  }

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn]

  tags = merge(local.monitoring_tags, {
    Severity   = "high"
    MetricType = "email-protection"
    AlertType  = "security"
  })
}

# -----------------------------------------------------------------------------
# Virus Detection Alarm
# -----------------------------------------------------------------------------
# Triggers when virus-infected emails are detected
# Indicates serious security threat

resource "aws_cloudwatch_metric_alarm" "virus_detected" {
  alarm_name          = "${var.project_name}-virus-detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EmailRejected"
  namespace           = "${var.project_name}/EmailProtection"
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 1 # Alert on ANY virus detection
  alarm_description   = "CRITICAL: Virus-infected emails detected"
  treat_missing_data  = "notBreaching"

  dimensions = {
    RejectionType = "virus_detected"
  }

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn]

  tags = merge(local.monitoring_tags, {
    Severity   = "critical"
    MetricType = "email-protection"
    AlertType  = "security"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Blocked Attachments Alarm
# -----------------------------------------------------------------------------
# Triggers when dangerous file types are blocked
# Indicates potential malware or phishing attempts

resource "aws_cloudwatch_metric_alarm" "blocked_attachments" {
  alarm_name          = "${var.project_name}-blocked-attachments"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EmailRejected"
  namespace           = "${var.project_name}/EmailProtection"
  period              = 3600 # 1 hour
  statistic           = "Sum"
  threshold           = 5 # Alert if more than 5 blocked attachments in 1 hour
  alarm_description   = "Dangerous attachment types blocked - possible malware or phishing attempt"
  treat_missing_data  = "notBreaching"

  dimensions = {
    RejectionType = "blocked_attachments"
  }

  alarm_actions = [aws_sns_topic.ses_notifications["bounce"].arn]

  tags = merge(local.monitoring_tags, {
    Severity   = "high"
    MetricType = "email-protection"
    AlertType  = "security"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "email_protection_alarms" {
  description = "Email protection CloudWatch alarm names"
  value = {
    large_files         = aws_cloudwatch_metric_alarm.large_file_rejections.alarm_name
    rate_limits         = aws_cloudwatch_metric_alarm.rate_limit_violations.alarm_name
    spam                = aws_cloudwatch_metric_alarm.spam_detected.alarm_name
    virus               = aws_cloudwatch_metric_alarm.virus_detected.alarm_name
    blocked_attachments = aws_cloudwatch_metric_alarm.blocked_attachments.alarm_name
  }
}
