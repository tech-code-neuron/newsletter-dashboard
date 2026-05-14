# ============================================================================
# REIT Sheet - Subscriber Engagement DynamoDB Table
# ============================================================================
# Stores aggregate engagement metrics per subscriber for segmentation
# and list health monitoring.
#
# Updated in real-time as events come in from SES.
#
# SOLID Principles:
#   - Single Responsibility: Per-subscriber engagement only
#   - Derived Data: Aggregated from email_events for performance

resource "aws_dynamodb_table" "subscriber_engagement" {
  name         = "${var.project_name}-subscriber-engagement"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "email"

  # Primary key: email
  attribute {
    name = "email"
    type = "S"
  }

  # For querying by engagement segment
  attribute {
    name = "segment"
    type = "S"
  }

  # For sorting by engagement score
  attribute {
    name = "engagement_score"
    type = "N"
  }

  # GSI: Query subscribers by segment
  # Use case: Find all "at_risk" subscribers for re-engagement campaign
  global_secondary_index {
    name            = "segment-engagement_score-index"
    hash_key        = "segment"
    range_key       = "engagement_score"
    projection_type = "ALL"
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Subscriber-Engagement"
    Description     = "Per-subscriber engagement metrics and segmentation"
    TableType       = "engagement-metrics"
    DataType        = "subscriber-engagement"
    PIIData         = "true"
    UpdateFrequency = "real-time"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "subscriber_engagement_table_name" {
  description = "Subscriber engagement table name"
  value       = aws_dynamodb_table.subscriber_engagement.name
}

output "subscriber_engagement_table_arn" {
  description = "Subscriber engagement table ARN"
  value       = aws_dynamodb_table.subscriber_engagement.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - email (String, Partition Key): Subscriber email address
#
# Lifetime Metrics:
#   - lifetime_sends: Total campaigns sent to this subscriber
#   - lifetime_opens: Total opens across all campaigns
#   - lifetime_clicks: Total clicks across all campaigns
#
# Recency Metrics:
#   - last_open_at: ISO timestamp of most recent open
#   - last_click_at: ISO timestamp of most recent click
#   - first_engaged_at: ISO timestamp of first ever open/click
#
# Segmentation:
#   - engagement_score: 0-100 calculated score
#   - segment: "highly_engaged", "engaged", "at_risk", "inactive"
#   - campaigns_opened: List of last 10 campaign_ids opened
#
# Segmentation Rules:
#   - highly_engaged: Opened 80%+ of last 10 campaigns
#   - engaged: Opened 40-79% of last 10 campaigns
#   - at_risk: Opened 10-39% of last 10 campaigns
#   - inactive: Opened <10% of last 10 OR no open in 90 days
#
# Update Pattern:
#   - Updated atomically on each open/click event
#   - Segment recalculated on each update
#
# ============================================================================
