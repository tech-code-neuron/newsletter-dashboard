# ============================================================================
# REIT Sheet - Email Tracking Table
# ============================================================================
# Tracks email processing through the entire pipeline
# Solves "Where is this email?" observability gap
#
# Architecture:
#   - PK: idempotency_key (unique per email)
#   - Tracks stage transitions: producer → parser → enricher → playwright → completed
#   - Enables queries: "Show all emails for ticker EPRT in last 24 hours"
#   - Enables monitoring: "Find stuck emails (no update in 1 hour)"
#
# Use Cases:
#   1. Debugging: "Where is Park Hotels $700M email?"
#   2. Monitoring: "How many emails stuck in enricher queue?"
#   3. Metrics: "Average time from producer to DynamoDB save"
#   4. Alerting: "Alert if email in same stage for >30 minutes"

resource "aws_dynamodb_table" "email_tracking" {
  name           = "${var.project_name}-email-tracking"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "idempotency_key"
  stream_enabled = false

  # Primary key: idempotency_key (unique per email)
  attribute {
    name = "idempotency_key"
    type = "S"
  }

  # GSI 1: Query by ticker + timestamp
  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "S"
  }

  global_secondary_index {
    name            = "ticker-updated-index"
    hash_key        = "ticker"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  # GSI 2: Query by stage (find all emails in a specific stage)
  attribute {
    name = "stage"
    type = "S"
  }

  global_secondary_index {
    name            = "stage-updated-index"
    hash_key        = "stage"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery (good practice for audit trail)
  point_in_time_recovery {
    enabled = true
  }

  # TTL: Auto-delete entries after 90 days (reduce storage costs)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.database_tags, {
    Name        = "${var.project_name}-email-tracking"
    Description = "Email processing pipeline observability"
    Purpose     = "track-email-stage-transitions"
    DataType    = "audit-trail"
    Retention   = "90-days-ttl"
    Criticality = "high"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "email_tracking_table_name" {
  description = "Email tracking table name"
  value       = aws_dynamodb_table.email_tracking.name
}

output "email_tracking_table_arn" {
  description = "Email tracking table ARN"
  value       = aws_dynamodb_table.email_tracking.arn
}
