# ============================================================================
# REIT Sheet - Newsletter Campaigns DynamoDB Table
# ============================================================================
# Stores newsletter campaign/send metadata and aggregate metrics
#
# Each newsletter send is tracked as a "campaign" with delivery and engagement
# metrics updated in real-time via SES event processing.
#
# SOLID Principles:
#   - Single Responsibility: Campaign-level metrics only
#   - Open/Closed: Atomic counter updates for real-time metrics

resource "aws_dynamodb_table" "campaigns" {
  name         = "${var.project_name}-campaigns"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "campaign_id"

  # Primary key: campaign_id (e.g., "campaign-2026-03-27" or UUID)
  attribute {
    name = "campaign_id"
    type = "S"
  }

  # For querying campaigns by status (draft, sending, sent)
  attribute {
    name = "status"
    type = "S"
  }

  # For sorting by send date
  attribute {
    name = "sent_at"
    type = "S"
  }

  # GSI: Query campaigns by status, sorted by date
  # Use case: Get all sent campaigns for dashboard
  global_secondary_index {
    name            = "status-sent_at-index"
    hash_key        = "status"
    range_key       = "sent_at"
    projection_type = "ALL"
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Newsletter-Campaigns"
    Description     = "Newsletter campaign metadata and aggregate metrics"
    TableType       = "campaign-tracking"
    DataType        = "campaign-metrics"
    AccessPattern   = "by-campaign-id-by-status"
    UpdateFrequency = "real-time"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "campaigns_table_name" {
  description = "Newsletter campaigns table name"
  value       = aws_dynamodb_table.campaigns.name
}

output "campaigns_table_arn" {
  description = "Newsletter campaigns table ARN"
  value       = aws_dynamodb_table.campaigns.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - campaign_id (String, Partition Key): "campaign-YYYY-MM-DD" or UUID
#
# Attributes:
#   - campaign_id: Unique campaign identifier
#   - subject: Email subject line
#   - status: "draft", "sending", "sent", "failed"
#   - sent_at: ISO 8601 timestamp when send started
#   - completed_at: ISO 8601 timestamp when send finished
#
# Delivery Counts (set once, after send completes):
#   - total_recipients: Total emails attempted
#   - delivered: Successfully delivered
#   - bounced: Hard + soft bounces
#   - complained: Spam complaints
#
# Engagement Counts (updated via atomic increments):
#   - unique_opens: Unique subscribers who opened
#   - total_opens: Total opens (including re-opens)
#   - unique_clicks: Unique subscribers who clicked
#   - total_clicks: Total click events
#   - unsubscribed: Unsubscribed from this campaign
#
# Calculated on read (not stored):
#   - open_rate: unique_opens / delivered * 100
#   - click_rate: unique_clicks / delivered * 100
#   - ctor: unique_clicks / unique_opens * 100 (click-to-open rate)
#   - bounce_rate: bounced / total_recipients * 100
#   - complaint_rate: complained / delivered * 100
#
# ============================================================================
