# ============================================================================
# REIT Sheet - SES Configuration Set for Newsletter Tracking
# ============================================================================
# Enables open/click tracking and event notifications for newsletters.
#
# SES handles:
#   - Automatic tracking pixel insertion for opens
#   - Automatic link wrapping for clicks
#   - Event delivery to SNS for processing
#
# SOLID Principles:
#   - Single Responsibility: Email tracking configuration only
#   - AWS Native: Uses SES built-in tracking (reliable, compliant)

# -----------------------------------------------------------------------------
# Configuration Set
# -----------------------------------------------------------------------------

resource "aws_sesv2_configuration_set" "newsletter" {
  configuration_set_name = "${var.project_name}-newsletter"

  # Custom tracking domain with HTTPS (served via CloudFront + ACM certificate)
  tracking_options {
    custom_redirect_domain = "newsletter.reitsheet.co"
    https_policy           = "OPTIONAL"
  }

  # Enable reputation metrics for monitoring
  reputation_options {
    reputation_metrics_enabled = true
  }

  # Enable sending
  sending_options {
    sending_enabled = true
  }

  # Delivery options
  delivery_options {
    tls_policy = "REQUIRE" # Always use TLS
  }

  # Suppression - use account-level (already configured)
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }

  tags = {
    Name        = "${var.project_name}-newsletter-config-set"
    Environment = var.environment
    Purpose     = "Newsletter email tracking and delivery"
  }
}

# -----------------------------------------------------------------------------
# SNS Topic for Email Events
# -----------------------------------------------------------------------------

resource "aws_sns_topic" "email_events" {
  name         = "${var.project_name}-email-events"
  display_name = "Newsletter Email Events"

  tags = {
    Name        = "${var.project_name}-email-events"
    Environment = var.environment
    Purpose     = "Receive SES email events for processing"
  }
}

# SNS topic policy to allow SES to publish
resource "aws_sns_topic_policy" "email_events" {
  arn = aws_sns_topic.email_events.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSESPublish"
        Effect    = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.email_events.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Event Destination - Send all events to SNS
# -----------------------------------------------------------------------------

resource "aws_sesv2_configuration_set_event_destination" "sns_events" {
  configuration_set_name = aws_sesv2_configuration_set.newsletter.configuration_set_name
  event_destination_name = "sns-all-events"

  event_destination {
    enabled = true

    # Track all event types for comprehensive analytics
    matching_event_types = [
      "SEND",
      "DELIVERY",
      "BOUNCE",
      "COMPLAINT",
      "OPEN",
      "CLICK",
      "RENDERING_FAILURE",
      "DELIVERY_DELAY",
      "SUBSCRIPTION"  # For List-Unsubscribe events
    ]

    sns_destination {
      topic_arn = aws_sns_topic.email_events.arn
    }
  }
}

# -----------------------------------------------------------------------------
# CloudWatch Event Destination (for dashboards/alarms)
# -----------------------------------------------------------------------------

resource "aws_sesv2_configuration_set_event_destination" "cloudwatch_metrics" {
  configuration_set_name = aws_sesv2_configuration_set.newsletter.configuration_set_name
  event_destination_name = "cloudwatch-metrics"

  event_destination {
    enabled = true

    matching_event_types = [
      "SEND",
      "DELIVERY",
      "BOUNCE",
      "COMPLAINT",
      "OPEN",
      "CLICK"
    ]

    cloud_watch_destination {
      dimension_configuration {
        default_dimension_value = "unknown"
        dimension_name          = "campaign_id"
        dimension_value_source  = "MESSAGE_TAG"
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "newsletter_configuration_set_name" {
  description = "SES Configuration Set name for newsletter sending"
  value       = aws_sesv2_configuration_set.newsletter.configuration_set_name
}

output "email_events_topic_arn" {
  description = "SNS topic ARN for email events"
  value       = aws_sns_topic.email_events.arn
}

output "email_events_topic_name" {
  description = "SNS topic name for email events"
  value       = aws_sns_topic.email_events.name
}

# ============================================================================
# Usage Notes
# ============================================================================
#
# When sending newsletter emails, include:
#
# 1. Configuration Set Name:
#    ConfigurationSetName = "reitsheet-newsletter"
#
# 2. Campaign Tag (for per-campaign metrics):
#    Tags = [{"Name": "campaign_id", "Value": "campaign-2026-03-27"}]
#
# 3. List-Unsubscribe Headers (for one-click unsubscribe):
#    Headers = [
#      {"Name": "List-Unsubscribe", "Value": "<https://reitsheet.co/unsubscribe?...>"},
#      {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"}
#    ]
#
# Event Processing:
#   - SNS topic triggers Lambda for DynamoDB updates
#   - CloudWatch metrics for real-time dashboards/alarms
#
# ============================================================================
