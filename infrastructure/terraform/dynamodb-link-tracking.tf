# ============================================================================
# REIT Sheet - Link Tracking DynamoDB Table
# ============================================================================
# Stores per-link click metrics for each campaign.
# Enables "top links" reporting and content performance analysis.
#
# SOLID Principles:
#   - Single Responsibility: Link-level metrics only
#   - Atomic Updates: Click counts updated via atomic increments

resource "aws_dynamodb_table" "link_tracking" {
  name         = "${var.project_name}-link-tracking"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "campaign_id"
  range_key    = "link_id"

  # Primary key: campaign_id + link_id
  attribute {
    name = "campaign_id"
    type = "S"
  }

  attribute {
    name = "link_id"
    type = "S"
  }

  # No GSIs needed - queries are always by campaign_id

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  # TTL: Auto-delete after 1 year (link data less critical than events)
  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Link-Tracking"
    Description     = "Per-link click metrics for campaigns"
    TableType       = "link-metrics"
    DataType        = "link-tracking"
    Retention       = "1-year"
    UpdateFrequency = "real-time"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "link_tracking_table_name" {
  description = "Link tracking table name"
  value       = aws_dynamodb_table.link_tracking.name
}

output "link_tracking_table_arn" {
  description = "Link tracking table ARN"
  value       = aws_dynamodb_table.link_tracking.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - campaign_id (String, Partition Key): Links to campaigns table
#   - link_id (String, Sort Key): "link-1", "link-2", etc. (position in email)
#
# Attributes:
#   - url: Original destination URL
#   - anchor_text: Link text (e.g., "Read more", company name)
#   - unique_clicks: Unique subscribers who clicked this link
#   - total_clicks: Total clicks (including repeat clicks)
#   - first_click_at: ISO timestamp of first click
#   - last_click_at: ISO timestamp of most recent click
#   - ttl: Unix timestamp for auto-deletion
#
# Calculated on read:
#   - click_rate: unique_clicks / campaign.unique_opens * 100
#
# Creation Pattern:
#   - Links created when campaign is sent (from HTML parsing)
#   - Click counts updated atomically on each click event
#
# Query Pattern:
#   - Get all links for a campaign: Query(campaign_id)
#   - Sort by total_clicks DESC for "top links" report
#
# ============================================================================
