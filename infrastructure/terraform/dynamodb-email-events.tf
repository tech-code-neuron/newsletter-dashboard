# ============================================================================
# REIT Sheet - Email Events DynamoDB Table (Immutable Audit Log)
# ============================================================================
# Stores all email events as an immutable audit log for GDPR compliance
# and engagement tracking.
#
# Events are APPEND-ONLY - never updated or deleted (except via TTL).
# This provides a complete audit trail for compliance purposes.
#
# SOLID Principles:
#   - Single Responsibility: Event logging only
#   - Immutability: Events are never modified after creation
#   - Privacy: Email stored as hash for queries, TTL for GDPR compliance

resource "aws_dynamodb_table" "email_events" {
  name         = "${var.project_name}-email-events"
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "event_id"
  range_key    = "timestamp"

  # Primary key: event_id (UUID) + timestamp
  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # For querying all events for a campaign
  attribute {
    name = "campaign_id"
    type = "S"
  }

  # For querying all events for a subscriber (hashed for privacy)
  attribute {
    name = "email_hash"
    type = "S"
  }

  # For querying by event type (opens, clicks, etc.)
  attribute {
    name = "event_type"
    type = "S"
  }

  # GSI: Get all events for a campaign
  global_secondary_index {
    name            = "campaign_id-timestamp-index"
    hash_key        = "campaign_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI: Get all events for a subscriber
  global_secondary_index {
    name            = "email_hash-timestamp-index"
    hash_key        = "email_hash"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI: Get all events of a type (for dashboards)
  global_secondary_index {
    name            = "event_type-timestamp-index"
    hash_key        = "event_type"
    range_key       = "timestamp"
    projection_type = "KEYS_ONLY" # Lightweight for counting
  }

  # TTL: Auto-delete events after 2 years (GDPR compliance)
  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.database_tags, {
    Name            = "REIT-Sheet-Email-Events"
    Description     = "Immutable email event audit log"
    TableType       = "event-log"
    DataType        = "email-events"
    Immutable       = "true"
    GDPRCompliant   = "true"
    Retention       = "2-years"
    PIIData         = "hashed-only"
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "email_events_table_name" {
  description = "Email events table name"
  value       = aws_dynamodb_table.email_events.name
}

output "email_events_table_arn" {
  description = "Email events table ARN"
  value       = aws_dynamodb_table.email_events.arn
}

# ============================================================================
# Schema Documentation
# ============================================================================
#
# Primary Key:
#   - event_id (String, Partition Key): UUID - immutable identifier
#   - timestamp (String, Sort Key): ISO 8601 with milliseconds
#
# Core Attributes:
#   - event_type: "send", "delivery", "bounce", "complaint", "open", "click", "unsubscribe"
#   - campaign_id: Links to campaigns table
#   - email_hash: SHA256 of email (for queries without exposing PII)
#   - ttl: Unix timestamp for auto-deletion (2 years from creation)
#
# Event-specific Attributes:
#   - link_url: For click events - destination URL
#   - link_id: For click events - position identifier (link-1, link-2, etc.)
#   - bounce_type: "Permanent", "Transient"
#   - complaint_type: "abuse", "not-spam"
#   - user_agent: For opens/clicks - client information
#   - ip_address: For opens/clicks - client IP
#
# Privacy Notes:
#   - Raw email is NOT stored in this table
#   - email_hash allows queries without exposing PII
#   - TTL ensures automatic deletion for GDPR compliance
#   - Events are immutable - anonymize on user deletion request
#
# ============================================================================
