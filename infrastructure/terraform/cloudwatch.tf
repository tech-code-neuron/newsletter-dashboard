# ============================================================================
# REIT Sheet - CloudWatch Monitoring Configuration
# ============================================================================
# Logging, metrics, and alarms for operational visibility
# - Log groups with retention policies
# - DLQ alarms for failure detection
# - Lambda metrics and insights

# -----------------------------------------------------------------------------
# Lambda Log Groups
# -----------------------------------------------------------------------------
# Explicit log groups with retention policies
# Prevents indefinite log retention and reduces costs

resource "aws_cloudwatch_log_group" "producer_logs" {
  name              = "/aws/lambda/${local.producer_function}"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name        = "REIT-Sheet-Producer-Lambda-Logs"
    Description = "CloudWatch-logs-for-S3-to-SQS-producer-Lambda-function"
    LogType     = "lambda-execution"
    Function    = local.producer_function
    Retention   = "${var.log_retention_days}-days"
  })
}

resource "aws_cloudwatch_log_group" "parser_logs" {
  name              = "/aws/lambda/${local.parser_function}"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name        = "REIT-Sheet-Parser-Lambda-Logs"
    Description = "CloudWatch-logs-for-email-parser-Lambda-function"
    LogType     = "lambda-execution"
    Function    = local.parser_function
    Retention   = "${var.log_retention_days}-days"
  })
}

resource "aws_cloudwatch_log_group" "scraper_logs" {
  name              = "/aws/lambda/${local.scraper_function}"
  retention_in_days = var.log_retention_days

  tags = merge(local.monitoring_tags, {
    Name        = "REIT-Sheet-Scraper-Lambda-Logs"
    Description = "CloudWatch-logs-for-web-scraper-Lambda-function"
    LogType     = "lambda-execution"
    Function    = local.scraper_function
    Retention   = "${var.log_retention_days}-days"
  })
}

# -----------------------------------------------------------------------------
# DLQ Alarms
# -----------------------------------------------------------------------------
# Alert when messages arrive in dead letter queues
# Indicates processing failures requiring investigation

resource "aws_cloudwatch_metric_alarm" "parse_dlq_alarm" {
  alarm_name          = local.parse_dlq_alarm
  alarm_description   = "Triggers when emails fail to parse and land in DLQ - indicates malformed emails or parser bugs"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.dlq_alarm_evaluation_periods
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = var.dlq_alarm_period_seconds
  statistic           = "Average"
  threshold           = var.dlq_alarm_threshold

  dimensions = {
    QueueName = aws_sqs_queue.email_parse_dlq.name
  }

  treat_missing_data = "notBreaching"

  tags = merge(local.monitoring_tags, {
    Name           = "REIT-Sheet-Parse-DLQ-Alarm"
    Description    = "Alert-on-email-parsing-failures"
    AlarmType      = "queue-depth"
    Severity       = "high"
    Queue          = local.parse_dlq_name
    ActionRequired = "investigate-parser-errors"
  })
}

resource "aws_cloudwatch_metric_alarm" "scrape_dlq_alarm" {
  alarm_name          = local.scrape_dlq_alarm
  alarm_description   = "Triggers when scraping jobs fail and land in DLQ - indicates timeouts, rate limits, or unreachable URLs"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.dlq_alarm_evaluation_periods
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = var.dlq_alarm_period_seconds
  statistic           = "Average"
  threshold           = var.dlq_alarm_threshold

  dimensions = {
    QueueName = aws_sqs_queue.scrape_dlq.name
  }

  treat_missing_data = "notBreaching"

  tags = merge(local.monitoring_tags, {
    Name           = "REIT-Sheet-Scrape-DLQ-Alarm"
    Description    = "Alert-on-web-scraping-failures"
    AlarmType      = "queue-depth"
    Severity       = "medium"
    Queue          = local.scrape_dlq_name
    ActionRequired = "investigate-scraper-errors"
  })
}

# -----------------------------------------------------------------------------
# Lambda Error Alarms
# -----------------------------------------------------------------------------
# Alert on Lambda function errors

resource "aws_cloudwatch_metric_alarm" "producer_errors" {
  alarm_name          = "${local.producer_function}-errors"
  alarm_description   = "Triggers when producer Lambda encounters errors - check S3 permissions and SQS access"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.dlq_alarm_evaluation_periods
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = var.dlq_alarm_period_seconds
  statistic           = "Sum"
  threshold           = var.dlq_alarm_threshold

  dimensions = {
    FunctionName = aws_lambda_function.producer.function_name
  }

  treat_missing_data = "notBreaching"

  tags = merge(local.monitoring_tags, {
    Name        = "REIT-Sheet-Producer-Lambda-Errors"
    Description = "Alert-on-producer-Lambda-errors"
    AlarmType   = "error-count"
    Severity    = "high"
    Function    = local.producer_function
  })
}

# ============================================================================
# TIER 1.3: ImportError Detection - Missing Dependencies Prevention
# ============================================================================
# Detects ImportError and ModuleNotFoundError in Lambda logs
# Alerts within 60 seconds of occurrence
#
# Why this exists:
#   - Catches missing dependencies immediately (not hours later)
#   - Would have detected 2026-03-13 parser incident in 60 seconds
#   - Prevents users from being affected by broken deployments

# SNS Topic for critical Lambda alerts
resource "aws_sns_topic" "lambda_critical_alerts" {
  name         = "reitsheet-lambda-critical-alerts"
  display_name = "REIT Newsletter Lambda Critical Alerts"

  tags = merge(local.monitoring_tags, {
    Name        = "REIT-Sheet-Lambda-Critical-Alerts"
    Description = "SNS-topic-for-critical-Lambda-errors"
    AlertType   = "critical-errors"
    Severity    = "critical"
  })
}

# TODO: Add email subscription for alerts
# resource "aws_sns_topic_subscription" "lambda_alerts_email" {
#   topic_arn = aws_sns_topic.lambda_critical_alerts.arn
#   protocol  = "email"
#   endpoint  = "your-email@example.com"
# }

# -----------------------------------------------------------------------------
# Parser Lambda - ImportError Detection
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "parser_import_errors" {
  name           = "parser-import-errors"
  log_group_name = aws_cloudwatch_log_group.parser_logs.name

  # Pattern matches ImportError or ModuleNotFoundError in logs
  pattern = "?ImportError ?ModuleNotFoundError"

  metric_transformation {
    name      = "ParserImportErrors"
    namespace = "REITSheet/Lambda/Critical"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "parser_import_error_alarm" {
  alarm_name          = "${local.parser_function}-import-errors"
  alarm_description   = "CRITICAL: Parser Lambda has ImportError - likely missing dependencies (like 2026-03-13 incident)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ParserImportErrors"
  namespace           = "REITSheet/Lambda/Critical"
  period              = 60 # 1 minute
  statistic           = "Sum"
  threshold           = 0 # Alert on ANY ImportError
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.lambda_critical_alerts.arn]
  ok_actions    = [aws_sns_topic.lambda_critical_alerts.arn]

  tags = merge(local.monitoring_tags, {
    Name           = "REIT-Sheet-Parser-ImportError-Alarm"
    Description    = "Alert-on-missing-dependencies"
    AlarmType      = "import-error"
    Severity       = "critical"
    Function       = local.parser_function
    ActionRequired = "check-deployment-package-rebuild-with-dependencies"
  })
}

# -----------------------------------------------------------------------------
# Enricher Lambda - ImportError Detection
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "enricher_import_errors" {
  name           = "enricher-import-errors"
  log_group_name = "/aws/lambda/${local.enricher_function}"

  pattern = "?ImportError ?ModuleNotFoundError"

  metric_transformation {
    name      = "EnricherImportErrors"
    namespace = "REITSheet/Lambda/Critical"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "enricher_import_error_alarm" {
  alarm_name          = "${local.enricher_function}-import-errors"
  alarm_description   = "CRITICAL: Enricher Lambda has ImportError - likely missing dependencies"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EnricherImportErrors"
  namespace           = "REITSheet/Lambda/Critical"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.lambda_critical_alerts.arn]
  ok_actions    = [aws_sns_topic.lambda_critical_alerts.arn]

  tags = merge(local.monitoring_tags, {
    Name           = "REIT-Sheet-Enricher-ImportError-Alarm"
    Description    = "Alert-on-missing-dependencies"
    AlarmType      = "import-error"
    Severity       = "critical"
    Function       = local.enricher_function
    ActionRequired = "check-deployment-package-rebuild-with-dependencies"
  })
}

# -----------------------------------------------------------------------------
# Scraper Lambda - ImportError Detection
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "scraper_import_errors" {
  name           = "scraper-import-errors"
  log_group_name = aws_cloudwatch_log_group.scraper_logs.name

  pattern = "?ImportError ?ModuleNotFoundError"

  metric_transformation {
    name      = "ScraperImportErrors"
    namespace = "REITSheet/Lambda/Critical"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "scraper_import_error_alarm" {
  alarm_name          = "${local.scraper_function}-import-errors"
  alarm_description   = "CRITICAL: Scraper Lambda has ImportError - likely missing dependencies"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ScraperImportErrors"
  namespace           = "REITSheet/Lambda/Critical"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.lambda_critical_alerts.arn]
  ok_actions    = [aws_sns_topic.lambda_critical_alerts.arn]

  tags = merge(local.monitoring_tags, {
    Name           = "REIT-Sheet-Scraper-ImportError-Alarm"
    Description    = "Alert-on-missing-dependencies"
    AlarmType      = "import-error"
    Severity       = "critical"
    Function       = local.scraper_function
    ActionRequired = "check-deployment-package-rebuild-with-dependencies"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "critical_alerts_topic_arn" {
  description = "ARN of the Lambda critical alerts SNS topic"
  value       = aws_sns_topic.lambda_critical_alerts.arn
}
